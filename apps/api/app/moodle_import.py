import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    Artifact,
    CaseFile,
    CaseStatus,
    Measurement,
    MoodleIdentity,
    MoodleSubmissionRecord,
)
from app.moodle_client import MoodleAPIError, MoodleClient, flatten_submission_files


@dataclass
class MoodleScopeData:
    site_name: str
    course_id: int
    course_name: str
    selected_cm_id: int | None
    selected_cm_ids: list[int]
    activities: list[dict[str, Any]]
    submissions_by_assignment: dict[int, list[dict[str, Any]]]
    requested_usernames: list[str] = field(default_factory=list)
    matched_users: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_scope(
    client: MoodleClient,
    settings: Settings,
    course_id: int | None,
    cm_id: int | None,
    cm_ids: list[int] | None = None,
    usernames: list[str] | None = None,
) -> MoodleScopeData:
    requested_course = course_id or settings.moodle_course_id
    requested_cms = list(dict.fromkeys(cm_ids or []))
    if cm_id and cm_id not in requested_cms:
        requested_cms.append(cm_id)
    if not requested_cms and settings.moodle_cm_id:
        requested_cms.append(settings.moodle_cm_id)
    resolved_course = client.resolve_course_id(
        requested_course, requested_cms[0] if requested_cms else None
    )
    site = client.site_info()
    course_name, assignments, warnings = client.assignments(resolved_course)
    if requested_cms:
        selected = set(requested_cms)
        assignments = [item for item in assignments if int(item.get("cmid", 0)) in selected]
        if not assignments:
            raise MoodleAPIError(
                f"Los cmid {requested_cms} no corresponden a tareas accesibles del curso {resolved_course}."
            )
        found = {int(item.get("cmid", 0)) for item in assignments}
        missing_cms = [value for value in requested_cms if value not in found]
        if missing_cms:
            warnings.extend(f"No se encontró el cmid {value} en el curso." for value in missing_cms)
    assignment_ids = [int(item["id"]) for item in assignments]
    requested_usernames = _clean_usernames(usernames or [])
    matched_users: list[dict[str, Any]] = []
    submission_warnings: list[str] = []
    if requested_usernames:
        matched_users = client.users_by_usernames(requested_usernames)
        found_names = {str(user.get("username", "")).lower() for user in matched_users}
        missing = [
            username for username in requested_usernames if username.lower() not in found_names
        ]
        submission_warnings.extend(
            f"No se encontró el username: {username}" for username in missing
        )
        submissions_by_assignment = {assignment_id: [] for assignment_id in assignment_ids}
        for assignment_id in assignment_ids:
            for user in matched_users:
                submission = client.submission_status(assignment_id, int(user["id"]))
                if submission:
                    submission.setdefault("userid", int(user["id"]))
                    submissions_by_assignment[assignment_id].append(submission)
    else:
        submission_groups, submission_warnings = client.submissions(assignment_ids)
        submissions_by_assignment = {
            int(group.get("assignmentid", 0)): group.get("submissions", [])
            for group in submission_groups
        }
    return MoodleScopeData(
        site_name=str(site.get("sitename") or site.get("siteurl") or "Moodle"),
        course_id=resolved_course,
        course_name=course_name,
        selected_cm_id=requested_cms[0] if len(requested_cms) == 1 else None,
        selected_cm_ids=requested_cms,
        activities=assignments,
        submissions_by_assignment=submissions_by_assignment,
        requested_usernames=requested_usernames,
        matched_users=matched_users,
        warnings=[*warnings, *submission_warnings],
    )


def preview_scope(scope: MoodleScopeData) -> dict[str, Any]:
    activities: list[dict[str, Any]] = []
    total_submissions = 0
    total_files = 0
    for assignment in scope.activities:
        assignment_id = int(assignment["id"])
        submissions = scope.submissions_by_assignment.get(assignment_id, [])
        file_count = sum(len(flatten_submission_files(item)) for item in submissions)
        total_submissions += len(submissions)
        total_files += file_count
        activities.append(
            {
                "assignment_id": assignment_id,
                "cm_id": int(assignment.get("cmid", 0)),
                "name": str(assignment.get("name", f"Tarea {assignment_id}")),
                "submission_count": len(submissions),
                "file_count": file_count,
            }
        )
    return {
        "site_name": scope.site_name,
        "course_id": scope.course_id,
        "course_name": scope.course_name,
        "selected_cm_id": scope.selected_cm_id,
        "selected_cm_ids": scope.selected_cm_ids,
        "requested_usernames": scope.requested_usernames,
        "matched_user_count": len(scope.matched_users),
        "activities": activities,
        "submission_count": total_submissions,
        "file_count": total_files,
        "warnings": scope.warnings,
    }


def import_scope(
    db: Session,
    client: MoodleClient,
    settings: Settings,
    *,
    course_id: int | None,
    cm_id: int | None,
    cm_ids: list[int] | None = None,
    measurement: Measurement,
    usernames: list[str] | None = None,
) -> dict[str, Any]:
    scope = resolve_scope(client, settings, course_id, cm_id, cm_ids, usernames)
    all_user_ids = sorted(
        {
            int(submission.get("userid", 0))
            for submissions in scope.submissions_by_assignment.values()
            for submission in submissions
            if int(submission.get("userid", 0))
        }
    )
    identity_users = scope.matched_users or client.users_by_ids(all_user_ids)
    identities = {int(user["id"]): user for user in identity_users}

    cases_created = 0
    cases_updated = 0
    artifacts_created = 0
    imported_case_ids: set[str] = set()
    site_id = hashlib.sha256(client.base_url.encode()).hexdigest()

    for assignment in scope.activities:
        assignment_id = int(assignment["id"])
        assignment_name = str(assignment.get("name", f"Tarea {assignment_id}"))
        for submission in scope.submissions_by_assignment.get(assignment_id, []):
            user_id = int(submission.get("userid", 0))
            if not user_id:
                continue
            teacher_code = _teacher_code(user_id, settings.moodle_webhook_secret)
            identity_data = identities.get(user_id, {})
            case = db.scalar(
                select(CaseFile).where(
                    CaseFile.moodle_site_id == site_id,
                    CaseFile.course_id == scope.course_id,
                    CaseFile.teacher_code == teacher_code,
                    CaseFile.measurement == measurement,
                )
            )
            if case is None:
                case = CaseFile(
                    teacher_code=teacher_code,
                    teacher_display_name=str(identity_data.get("fullname") or "") or None,
                    moodle_site_id=site_id,
                    course_id=scope.course_id,
                    course_name=scope.course_name,
                    submission_id=int(submission.get("id", 0)),
                    manifest_version=max(1, int(submission.get("attemptnumber", 0)) + 1),
                    measurement=measurement,
                    status=CaseStatus.processing,
                )
                db.add(case)
                db.flush()
                cases_created += 1
            else:
                cases_updated += 1

            identity = db.scalar(select(MoodleIdentity).where(MoodleIdentity.case_id == case.id))
            if identity is None:
                identity = MoodleIdentity(case_id=case.id, moodle_user_id=user_id)
                db.add(identity)
            identity.username = str(identity_data.get("username") or "") or None
            identity.full_name = str(identity_data.get("fullname") or "") or None
            identity.email = (
                str(identity_data.get("email") or "") or None
                if settings.moodle_include_names
                else None
            )
            case.teacher_display_name = identity.full_name

            imported_case_ids.add(case.id)
            attempt_number = int(submission.get("attemptnumber", 0))
            submission_id = int(submission.get("id", 0))
            cm_id = int(assignment.get("cmid", 0))
            delivery = db.scalar(
                select(MoodleSubmissionRecord).where(
                    MoodleSubmissionRecord.case_id == case.id,
                    MoodleSubmissionRecord.assignment_id == assignment_id,
                    MoodleSubmissionRecord.submission_id == submission_id,
                    MoodleSubmissionRecord.attempt_number == attempt_number,
                )
            )
            if delivery is None:
                delivery = MoodleSubmissionRecord(
                    case_id=case.id,
                    course_id=scope.course_id,
                    cm_id=cm_id,
                    assignment_id=assignment_id,
                    submission_id=submission_id,
                    activity_name=assignment_name,
                    attempt_number=attempt_number,
                )
                db.add(delivery)
            delivery.status = str(submission.get("status") or "unknown")
            delivery.time_modified = _moodle_datetime(submission.get("timemodified"))

            existing_artifacts = list(
                db.scalars(select(Artifact).where(Artifact.case_id == case.id))
            )
            artifacts_by_hash = {artifact.content_hash: artifact for artifact in existing_artifacts}
            files = flatten_submission_files(submission)
            delivery_artifact_ids: list[str] = []
            for file in files:
                content_hash = str(file.get("contenthash") or _fallback_hash(file))
                if content_hash in artifacts_by_hash:
                    delivery_artifact_ids.append(artifacts_by_hash[content_hash].id)
                    continue
                artifact = Artifact(
                    case_id=case.id,
                    evidence_type=classify_evidence(assignment_name, str(file.get("filename", ""))),
                    filename=str(file.get("filename") or "archivo_sin_nombre"),
                    mime_type=str(file.get("mimetype") or "application/octet-stream"),
                    source_url=_clean_file_url(str(file.get("fileurl") or "")),
                    content_hash=content_hash,
                    processing_status="PENDING_DOWNLOAD",
                    extracted_summary=f"Importado desde la actividad: {assignment_name}",
                )
                db.add(artifact)
                db.flush()
                artifacts_by_hash[content_hash] = artifact
                delivery_artifact_ids.append(artifact.id)
                artifacts_created += 1
            delivery.artifact_ids = delivery_artifact_ids
            if files:
                case.status = CaseStatus.ready

    db.commit()
    return {
        "course_id": scope.course_id,
        "selected_cm_id": scope.selected_cm_id,
        "selected_cm_ids": scope.selected_cm_ids,
        "cases_created": cases_created,
        "cases_updated": cases_updated,
        "artifacts_created": artifacts_created,
        "case_ids": sorted(imported_case_ids),
        "warnings": scope.warnings,
    }


def classify_evidence(assignment_name: str, filename: str) -> str:
    text = _normalise(f"{assignment_name} {filename}")
    patterns = [
        ("NARRACION_REFLEXIVA", ("narracion", "reflexiva")),
        ("VIDEO_CLASE", ("video", "clase")),
        ("SESION_PRIORIZADA", ("sesion", "priorizada")),
        ("UNIDAD_DIDACTICA", ("unidad", "didactica")),
        ("INSTRUMENTO_EVALUACION", ("rubrica", "lista de cotejo", "instrumento")),
        ("RETROALIMENTACION", ("retroalimentacion",)),
        ("TRABAJOS_ESTUDIANTES", ("estudiante", "producto", "trabajo")),
        ("SESION_APRENDIZAJE", ("sesion",)),
    ]
    for evidence_type, keywords in patterns:
        if any(keyword in text for keyword in keywords):
            return evidence_type
    return "OTRA_EVIDENCIA"


def _teacher_code(user_id: int, secret: str) -> str:
    digest = hashlib.sha256(f"{secret}:{user_id}".encode()).hexdigest()[:16].upper()
    return f"DOC-{digest}"


def _normalise(value: str) -> str:
    replacements = str.maketrans("áéíóúüñ", "aeiouun")
    return re.sub(r"\s+", " ", value.lower().translate(replacements)).strip()


def _clean_file_url(value: str) -> str | None:
    if not value:
        return None
    return value.split("?token=", 1)[0].split("&token=", 1)[0]


def _fallback_hash(file: dict[str, Any]) -> str:
    raw = f"{file.get('filename')}:{file.get('filesize')}:{file.get('timemodified')}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _clean_usernames(usernames: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in usernames:
        username = raw.strip()
        key = username.lower()
        if username and key not in seen:
            cleaned.append(username)
            seen.add(key)
    return cleaned


def _moodle_datetime(value: Any) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC) if timestamp > 0 else None
