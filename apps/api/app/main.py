import hashlib
import hmac
import json
from collections.abc import Generator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from kombu.exceptions import OperationalError
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.ai_analysis import (
    AIServiceError,
    aggregate_analysis,
    ai_configured,
    analyze_case,
    answer_case_question,
)
from app.analytics_engine import build_multimodal_analytics
from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db
from app.file_proxy import stream_artifact
from app.models import (
    ArtifactText,
    ActivityReviewCriterion,
    Artifact,
    CaseAIAnalysis,
    CaseFile,
    CaseStatus,
    Citation,
    HumanReview,
    IndicatorResult,
    IngestionEvent,
    MoodleSubmissionRecord,
    RubricAssessment,
    RubricCriterion,
)
from app.moodle_client import MoodleAPIError, MoodleClient
from app.moodle_import import import_scope, preview_scope, resolve_scope
from app.rubric import seed_rubric
from app.similarity import prepare_texts
from app.schemas import (
    SimilarityPrepareOut,
    SimilarityPrepareRequest,
    ActivityCriterionOut,
    ActivityCriterionUpsert,
    AnalysisBatchRequest,
    AnalysisQueuedOut,
    AnalyticsOverviewOut,
    CaseAIAnalysisOut,
    CaseDetail,
    CaseQuery,
    CaseSummary,
    EventAccepted,
    GroundedAnswer,
    MoodleEvent,
    MoodleImportOut,
    MoodleImportRequest,
    MoodlePreviewOut,
    MoodleScope,
    ReviewCreate,
    ReviewOut,
    RubricAssessmentOut,
    RubricCriterionOut,
    RubricValidationCreate,
)
from app.services import case_query, grounded_demo_answer, seed_demo_case

settings = get_settings()
DbSession = Annotated[Session, Depends(get_db)]
MoodleSignature = Annotated[str | None, Header()]


def get_moodle_client() -> Generator[MoodleClient, None, None]:
    try:
        client = MoodleClient(settings)
    except MoodleAPIError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    try:
        yield client
    finally:
        client.close()


MoodleClientDep = Annotated[MoodleClient, Depends(get_moodle_client)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_rubric(db)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "difods-copilot-api"}


@app.get(f"{settings.api_prefix}/system/database")
def database_info() -> dict[str, object]:
    inspector = inspect(engine)
    return {
        "dialect": engine.dialect.name,
        "database": engine.url.database,
        "host": engine.url.host,
        "port": engine.url.port,
        "tables": sorted(inspector.get_table_names()),
    }


@app.get(f"{settings.api_prefix}/ai/config")
def ai_config() -> dict[str, object]:
    return {
        "configured": ai_configured(settings),
        "enabled": settings.ai_analysis_enabled,
        "auto_analysis_enabled": settings.ai_auto_analysis_enabled,
        "deployment": settings.azure_openai_deployment if ai_configured(settings) else None,
    }


@app.get(f"{settings.api_prefix}/moodle/config")
def moodle_config() -> dict[str, object]:
    return {
        "configured": bool(settings.moodle_base_url and settings.moodle_token),
        "base_url": settings.moodle_base_url,
        "default_course_id": settings.moodle_course_id,
        "default_cm_id": settings.moodle_cm_id,
        "includes_names": settings.moodle_include_names,
    }


@app.get(f"{settings.api_prefix}/moodle/connectivity")
def moodle_connectivity(client: MoodleClientDep) -> dict[str, object]:
    try:
        info = client.site_info()
    except MoodleAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        "connected": True,
        "site_name": info.get("sitename"),
        "site_url": info.get("siteurl"),
        "release": info.get("release"),
        "functions": info.get("functions", []),
    }


@app.post(f"{settings.api_prefix}/moodle/preview", response_model=MoodlePreviewOut)
def moodle_preview(payload: MoodleScope, client: MoodleClientDep) -> dict[str, object]:
    try:
        scope = resolve_scope(
            client,
            settings,
            payload.course_id,
            payload.cm_id,
            cm_ids=payload.cm_ids,
            usernames=payload.usernames,
        )
        return preview_scope(scope)
    except MoodleAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post(f"{settings.api_prefix}/moodle/import", response_model=MoodleImportOut)
def moodle_import(
    payload: MoodleImportRequest,
    db: DbSession,
    client: MoodleClientDep,
) -> dict[str, object]:
    try:
        result = import_scope(
            db,
            client,
            settings,
            course_id=payload.course_id,
            cm_id=payload.cm_id,
            cm_ids=payload.cm_ids,
            measurement=payload.measurement,
            usernames=payload.usernames,
        )
        if (
            settings.ai_analysis_enabled
            and settings.ai_auto_analysis_enabled
            and ai_configured(settings)
        ):
            from app.worker import process_submission

            queued = 0
            for case_id in result["case_ids"]:
                try:
                    process_submission.delay(case_id)
                    queued += 1
                except (OperationalError, ConnectionError):
                    result["warnings"].append(
                        f"El expediente {case_id} se importó, pero no pudo encolarse para análisis."
                    )
            result["warnings"].append(f"{queued} expediente(s) enviados al análisis IA.")
        return result
    except MoodleAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get(
    f"{settings.api_prefix}/activity-criteria",
    response_model=list[ActivityCriterionOut],
)
def list_activity_criteria(course_id: int, db: DbSession) -> list[ActivityReviewCriterion]:
    return list(
        db.scalars(
            select(ActivityReviewCriterion)
            .where(ActivityReviewCriterion.course_id == course_id)
            .order_by(ActivityReviewCriterion.cm_id)
        )
    )


@app.put(
    f"{settings.api_prefix}/activity-criteria/{{cm_id}}",
    response_model=ActivityCriterionOut,
)
def upsert_activity_criterion(
    cm_id: int, payload: ActivityCriterionUpsert, db: DbSession
) -> ActivityReviewCriterion:
    if cm_id != payload.cm_id:
        raise HTTPException(status_code=400, detail="El cmid de la ruta no coincide.")
    criterion = db.scalar(
        select(ActivityReviewCriterion).where(
            ActivityReviewCriterion.course_id == payload.course_id,
            ActivityReviewCriterion.cm_id == cm_id,
        )
    )
    if criterion is None:
        criterion = ActivityReviewCriterion(**payload.model_dump())
        db.add(criterion)
    else:
        for key, value in payload.model_dump().items():
            setattr(criterion, key, value)
    db.commit()
    db.refresh(criterion)
    return criterion


@app.get(f"{settings.api_prefix}/rubric", response_model=list[RubricCriterionOut])
def list_rubric(db: DbSession) -> list[RubricCriterion]:
    return list(
        db.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.active.is_(True))
            .order_by(RubricCriterion.display_order)
        )
    )


@app.put(
    f"{settings.api_prefix}/rubric-assessments/{{assessment_id}}/validation",
    response_model=RubricAssessmentOut,
)
def validate_rubric_assessment(
    assessment_id: str, payload: RubricValidationCreate, db: DbSession
) -> RubricAssessment:
    assessment = db.get(RubricAssessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Valoración de rúbrica no encontrada")
    assessment.validated_level = payload.validated_level
    assessment.reviewer_note = payload.reviewer_note
    assessment.validation_status = "VALIDATED_BY_HUMAN"
    db.commit()
    return db.scalar(
        select(RubricAssessment)
        .options(selectinload(RubricAssessment.criterion_ref))
        .where(RubricAssessment.id == assessment_id)
    )


@app.get(f"{settings.api_prefix}/cases", response_model=list[CaseSummary])
def list_cases(db: DbSession) -> list[CaseFile]:
    return list(db.scalars(select(CaseFile).order_by(CaseFile.updated_at.desc())))


@app.get(f"{settings.api_prefix}/cases/{{case_id}}", response_model=CaseDetail)
def get_case(case_id: str, db: DbSession) -> CaseFile:
    case = db.scalar(case_query().where(CaseFile.id == case_id))
    if not case:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return case


@app.delete(f"{settings.api_prefix}/cases/{{case_id}}/activities/{{cm_id}}")
def remove_case_activity(case_id: str, cm_id: int, db: DbSession) -> dict[str, object]:
    case = db.scalar(case_query().where(CaseFile.id == case_id))
    if not case:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    deliveries = [item for item in case.moodle_submissions if item.cm_id == cm_id]
    if not deliveries:
        raise HTTPException(status_code=404, detail=f"El expediente no contiene el CMID {cm_id}.")

    removed_artifact_ids = {value for item in deliveries for value in item.artifact_ids}
    remaining = [item for item in case.moodle_submissions if item.cm_id != cm_id]
    retained_artifact_ids = {value for item in remaining for value in item.artifact_ids}
    orphan_ids = removed_artifact_ids - retained_artifact_ids

    for citation in list(db.scalars(select(Citation).where(Citation.artifact_id.in_(orphan_ids)))):
        db.delete(citation)
    removed_files = 0
    for artifact_id in orphan_ids:
        artifact = db.get(Artifact, artifact_id)
        if artifact:
            db.delete(artifact)
            removed_files += 1
    for delivery in deliveries:
        db.delete(delivery)
    for assessment in list(
        db.scalars(
            select(RubricAssessment).where(
                RubricAssessment.case_id == case_id,
                RubricAssessment.cm_id == cm_id,
            )
        )
    ):
        db.delete(assessment)
    if case.ai_analysis:
        db.delete(case.ai_analysis)
    case.executive_summary = None
    case.status = CaseStatus.ready if remaining else CaseStatus.partial
    db.commit()
    return {
        "removed": True,
        "case_id": case_id,
        "cm_id": cm_id,
        "deliveries_removed": len(deliveries),
        "orphan_files_removed": removed_files,
        "moodle_unchanged": True,
    }


@app.get(f"{settings.api_prefix}/artifacts/{{artifact_id}}/content")
async def get_artifact_content(
    artifact_id: str,
    request: Request,
    db: DbSession,
) -> Response:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return await stream_artifact(artifact, settings, request.headers.get("range"))


@app.get(f"{settings.api_prefix}/analytics/overview", response_model=AnalyticsOverviewOut)
def analytics_overview(db: DbSession, case_ids: str | None = None) -> dict[str, object]:
    cases = list(db.scalars(select(CaseFile)))
    requested_ids = {value.strip() for value in (case_ids or "").split(",") if value.strip()}
    if requested_ids:
        cases = [case for case in cases if case.id in requested_ids]
    selected_ids = {case.id for case in cases}
    deliveries = list(
        db.scalars(
            select(MoodleSubmissionRecord).where(
                MoodleSubmissionRecord.case_id.in_(selected_ids)
            )
        )
    ) if selected_ids else []
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.case_id.in_(selected_ids)))
    ) if selected_ids else []
    analyses = list(
        db.scalars(select(CaseAIAnalysis).where(CaseAIAnalysis.case_id.in_(selected_ids)))
    ) if selected_ids else []
    rubric_assessments = list(
        db.scalars(
            select(RubricAssessment)
            .options(selectinload(RubricAssessment.criterion_ref))
            .where(RubricAssessment.case_id.in_(selected_ids))
        )
    ) if selected_ids else []
    teacher_keys = {
        case.identity.moodle_user_id if case.identity else case.teacher_code for case in cases
    }
    activity_map: dict[tuple[int, str], dict[str, int | str]] = {}
    for delivery in deliveries:
        key = (delivery.cm_id, delivery.activity_name)
        row = activity_map.setdefault(
            key,
            {
                "cm_id": delivery.cm_id,
                "activity_name": delivery.activity_name,
                "submissions": 0,
                "submitted": 0,
                "files": 0,
            },
        )
        row["submissions"] = int(row["submissions"]) + 1
        row["files"] = int(row["files"]) + len(delivery.artifact_ids)
        if delivery.status.lower() == "submitted":
            row["submitted"] = int(row["submitted"]) + 1
    evidence_counts: dict[str, int] = {}
    for artifact in artifacts:
        evidence_counts[artifact.evidence_type] = evidence_counts.get(artifact.evidence_type, 0) + 1
    reviewed_signals = (
        db.scalar(
            select(func.count(HumanReview.id))
            .join(IndicatorResult, HumanReview.indicator_id == IndicatorResult.id)
            .where(IndicatorResult.case_id.in_(selected_ids))
        )
        if selected_ids
        else 0
    ) or 0
    ai_metrics = aggregate_analysis(analyses)
    texts = {
        row.artifact_id: row.text
        for row in db.scalars(
            select(ArtifactText).where(
                ArtifactText.artifact_id.in_([artifact.id for artifact in artifacts]),
                ArtifactText.status == "EXTRACTED",
            )
        )
        if row.text
    } if artifacts else {}
    multimodal_metrics = build_multimodal_analytics(
        cases, deliveries, artifacts, analyses, rubric_assessments, texts
    )
    analysis_by_case = {item.case_id: item for item in analyses}
    case_by_id = {case.id: case for case in cases}
    artifact_by_id = {artifact.id: artifact for artifact in artifacts}
    evidence_by_cmid_map: dict[tuple[int, str, str], int] = {}
    video_comparison: list[dict[str, object]] = []
    for delivery in deliveries:
        for artifact_id in delivery.artifact_ids:
            artifact = artifact_by_id.get(artifact_id)
            if not artifact:
                continue
            evidence_key = (delivery.cm_id, delivery.activity_name, artifact.evidence_type)
            evidence_by_cmid_map[evidence_key] = evidence_by_cmid_map.get(evidence_key, 0) + 1
            technical_analysis = artifact.technical_analysis
            if technical_analysis and technical_analysis.modality == "VIDEO":
                metrics = technical_analysis.metrics or {}
                case = case_by_id.get(delivery.case_id)
                video_comparison.append(
                    {
                        "case_id": delivery.case_id,
                        "teacher": case.teacher_display_name or case.teacher_code if case else delivery.case_id,
                        "cm_id": delivery.cm_id,
                        "activity_name": delivery.activity_name,
                        "filename": artifact.filename,
                        "duration_seconds": metrics.get("duration_seconds"),
                        "width": metrics.get("width"),
                        "height": metrics.get("height"),
                        "fps": metrics.get("fps"),
                        "has_audio": metrics.get("has_audio"),
                        "sampled_frames": metrics.get("sampled_frames"),
                        "status": technical_analysis.status,
                    }
                )
    teacher_analysis = []
    for case in cases:
        analysis = analysis_by_case.get(case.id)
        findings = analysis.findings or [] if analysis else []
        coherence = next(
            (item for item in findings if item.get("type") == "CROSS_CMID_COHERENCE"),
            None,
        )
        cmid_reviews = [item for item in findings if item.get("type") == "CMID_REVIEW"]
        scores = [float(item["score"]) for item in cmid_reviews if item.get("score") is not None]
        teacher_analysis.append(
            {
                "case_id": case.id,
                "teacher": case.teacher_display_name or case.teacher_code,
                "username": case.identity.username if case.identity else None,
                "status": analysis.status if analysis else "PENDING",
                "risk_level": analysis.risk_level if analysis else "UNKNOWN",
                "cluster": analysis.cluster_label if analysis else None,
                "findings": len(analysis.findings or []) if analysis else 0,
                "average_cmid_score": round(sum(scores) / len(scores), 1) if scores else None,
                "coherence_score": coherence.get("score") if coherence else None,
                "cmid_scores": [
                    {
                        "cm_id": item.get("cm_id"),
                        "score": item.get("score"),
                        "similarity_score": item.get("similarity_score"),
                        "validation_status": item.get("validation_status"),
                    }
                    for item in cmid_reviews
                ],
            }
        )
    return {
        "teachers": len(teacher_keys),
        "cases": len(cases),
        "submissions": len(deliveries),
        "submitted": sum(item.status.lower() == "submitted" for item in deliveries),
        "files": len(artifacts),
        "reviewed_signals": reviewed_signals,
        "activities": sorted(activity_map.values(), key=lambda item: str(item["activity_name"])),
        "evidence_types": [
            {"evidence_type": key, "count": value} for key, value in sorted(evidence_counts.items())
        ],
        **ai_metrics,
        "pending_analysis": len(cases) - int(ai_metrics["analyzed_cases"]),
        "teacher_analysis": teacher_analysis,
        "evidence_by_cmid": [
            {
                "cm_id": key[0],
                "activity_name": key[1],
                "evidence_type": key[2],
                "count": value,
            }
            for key, value in sorted(evidence_by_cmid_map.items())
        ],
        "video_comparison": video_comparison,
        **multimodal_metrics,
    }


@app.post(
    f"{settings.api_prefix}/cases/{{case_id}}/analyze",
    response_model=CaseAIAnalysisOut,
)
def analyze_single_case(case_id: str, db: DbSession) -> CaseAIAnalysis:
    if not settings.ai_analysis_enabled:
        raise HTTPException(status_code=503, detail="El análisis IA está desactivado.")
    try:
        return analyze_case(db, settings, case_id, force=True)
    except AIServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post(f"{settings.api_prefix}/analysis/run", response_model=AnalysisQueuedOut)
def queue_analysis(payload: AnalysisBatchRequest, db: DbSession) -> dict[str, object]:
    if not settings.ai_analysis_enabled:
        raise HTTPException(status_code=503, detail="El análisis IA está desactivado.")
    if not ai_configured(settings):
        raise HTTPException(status_code=503, detail="Azure OpenAI no está configurado en la API.")
    case_ids = payload.case_ids or list(db.scalars(select(CaseFile.id)))
    existing = set(db.scalars(select(CaseFile.id).where(CaseFile.id.in_(case_ids))))
    selected = [case_id for case_id in case_ids if case_id in existing]
    from app.worker import process_submission

    try:
        for case_id in selected:
            process_submission.delay(case_id, payload.force)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar con la cola: {error}") from error
    return {"queued": len(selected), "case_ids": selected}


@app.post(f"{settings.api_prefix}/analysis/prepare-similarity", response_model=SimilarityPrepareOut)
def prepare_similarity(payload: SimilarityPrepareRequest, db: DbSession) -> dict[str, int]:
    case_ids = payload.case_ids or list(db.scalars(select(CaseFile.id)))
    return prepare_texts(
        db, settings, case_ids, batch_size=payload.batch_size, retry_failed=payload.retry_failed
    )


@app.post(f"{settings.api_prefix}/demo/seed", response_model=CaseDetail)
def create_demo(db: DbSession) -> CaseFile:
    return seed_demo_case(db)


@app.post(
    f"{settings.api_prefix}/indicator-results/{{indicator_id}}/reviews",
    response_model=ReviewOut,
    status_code=201,
)
def review_indicator(indicator_id: str, payload: ReviewCreate, db: DbSession) -> HumanReview:
    indicator = db.get(IndicatorResult, indicator_id)
    if not indicator:
        raise HTTPException(status_code=404, detail="Indicador no encontrado")
    review = HumanReview(indicator_id=indicator_id, **payload.model_dump())
    db.add(review)
    case = db.get(CaseFile, indicator.case_id)
    if case and case.status == CaseStatus.ready:
        case.status = CaseStatus.in_review
    db.commit()
    db.refresh(review)
    return review


@app.post(f"{settings.api_prefix}/cases/{{case_id}}/queries", response_model=GroundedAnswer)
def query_case(case_id: str, payload: CaseQuery, db: DbSession) -> GroundedAnswer:
    case = db.scalar(case_query().where(CaseFile.id == case_id))
    if not case:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    if (not settings.ai_analysis_enabled or not ai_configured(settings)) and case.indicators:
        answer, citations = grounded_demo_answer(case, payload.question)
        return GroundedAnswer(
            answer=answer,
            limitation="Modo demostración: Azure OpenAI no está habilitado.",
            citations=citations,
        )
    try:
        answer, sources = answer_case_question(db, settings, case, payload.question)
    except AIServiceError as error:
        if not ai_configured(settings) and case.indicators:
            answer, citations = grounded_demo_answer(case, payload.question)
            return GroundedAnswer(
                answer=answer,
                limitation="Modo demostración: Azure OpenAI no está configurado.",
                citations=citations,
            )
        raise HTTPException(status_code=502, detail=str(error)) from error
    return GroundedAnswer(
        answer=answer,
        limitation="Resultado asistivo basado solo en las evidencias procesadas; requiere validación humana.",
        citations=[],
        sources=sources,
    )


@app.post(f"{settings.api_prefix}/moodle/events", response_model=EventAccepted, status_code=202)
def receive_moodle_event(
    payload: MoodleEvent,
    response: Response,
    db: DbSession,
    x_moodle_signature: MoodleSignature = None,
) -> EventAccepted:
    body = payload.model_dump(mode="json")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(
        settings.moodle_webhook_secret.encode(), canonical, hashlib.sha256
    ).hexdigest()
    if settings.app_env != "development" and not hmac.compare_digest(
        x_moodle_signature or "", expected
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Firma inválida")

    existing = db.get(IngestionEvent, payload.event_id)
    if existing:
        response.status_code = status.HTTP_200_OK
        case = db.scalar(select(CaseFile).where(CaseFile.submission_id == payload.submission_id))
        return EventAccepted(
            event_id=payload.event_id,
            accepted=True,
            duplicate=True,
            case_id=case.id if case else None,
        )

    case = db.scalar(
        select(CaseFile).where(
            CaseFile.moodle_site_id == payload.moodle_site_id,
            CaseFile.submission_id == payload.submission_id,
            CaseFile.manifest_version == payload.manifest_version,
        )
    )
    if not case:
        case = CaseFile(
            teacher_code=payload.teacher_pseudonym_id,
            moodle_site_id=payload.moodle_site_id,
            course_id=payload.course_id,
            course_name=payload.course_name,
            submission_id=payload.submission_id,
            manifest_version=payload.manifest_version,
            measurement=payload.measurement,
            status=CaseStatus.discovered,
            region=payload.region,
            ugel=payload.ugel,
            education_level=payload.education_level,
        )
        db.add(case)
        db.flush()

    db.add(
        IngestionEvent(
            event_id=payload.event_id,
            event_type=payload.event_type,
            payload=body,
            correlation_id=payload.correlation_id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        response.status_code = status.HTTP_200_OK
        return EventAccepted(
            event_id=payload.event_id, accepted=True, duplicate=True, case_id=case.id
        )
    return EventAccepted(event_id=payload.event_id, accepted=True, duplicate=False, case_id=case.id)
