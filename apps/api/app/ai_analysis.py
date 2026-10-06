import base64
import io
import json
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    ActivityReviewCriterion,
    Artifact,
    ArtifactTechnicalAnalysis,
    CaseAIAnalysis,
    CaseFile,
    CaseStatus,
    RubricAssessment,
    RubricCriterion,
)
from app.services import case_query


class AIServiceError(RuntimeError):
    pass


def ai_configured(settings: Settings) -> bool:
    return bool(
        settings.azure_openai_api_key
        and settings.azure_openai_endpoint
        and settings.azure_openai_deployment
    )


def _azure_json(settings: Settings, messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not ai_configured(settings):
        raise AIServiceError(
            "Azure OpenAI no está configurado. Verifica AZURE_OPENAI_API_KEY, "
            "AZURE_OPENAI_ENDPOINT y AZURE_OPENAI_DEPLOYMENT."
        )
    endpoint = settings.azure_openai_endpoint.rstrip("/")
    deployment = settings.azure_openai_deployment
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions"
    try:
        response = httpx.post(
            url,
            params={"api-version": settings.azure_openai_api_version},
            headers={"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"},
            json={
                "messages": messages,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=httpx.Timeout(settings.ai_request_timeout_seconds, connect=20),
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as error:
        detail = str(error)
        if isinstance(error, httpx.HTTPStatusError):
            detail = error.response.text[:500]
        raise AIServiceError(f"Azure OpenAI no pudo completar la solicitud: {detail}") from error


def _download_artifact(artifact: Artifact, settings: Settings) -> bytes:
    if not artifact.source_url:
        raise AIServiceError("El archivo no tiene URL Moodle.")
    source = urlparse(artifact.source_url)
    allowed = urlparse(settings.moodle_base_url)
    if source.scheme != "https" or source.hostname != allowed.hostname:
        raise AIServiceError("La URL no pertenece al Moodle configurado.")
    limit_mb = settings.ai_max_video_mb if artifact.mime_type.startswith("video/") else settings.ai_max_file_mb
    max_bytes = limit_mb * 1024 * 1024
    try:
        with httpx.stream(
            "GET",
            artifact.source_url,
            params={"token": settings.moodle_token},
            follow_redirects=True,
            timeout=httpx.Timeout(settings.moodle_timeout_seconds, connect=20),
        ) as response:
            response.raise_for_status()
            declared = int(response.headers.get("content-length", "0") or 0)
            if declared > max_bytes:
                raise AIServiceError(f"Archivo mayor al límite de {limit_mb} MB.")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise AIServiceError(f"Archivo mayor al límite de {limit_mb} MB.")
                chunks.append(chunk)
            return b"".join(chunks)
    except httpx.HTTPError as error:
        raise AIServiceError(f"No se pudo descargar desde Moodle: {error}") from error


def _extract_text(artifact: Artifact, payload: bytes, limit: int) -> tuple[str, int | None]:
    mime = artifact.mime_type.lower()
    name = artifact.filename.lower()
    if mime == "application/pdf" or name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text[:limit], len(reader.pages)
    if "wordprocessingml" in mime or name.endswith(".docx"):
        from docx import Document

        document = Document(io.BytesIO(payload))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return text[:limit], None
    if mime.startswith("text/") or name.endswith((".txt", ".csv")):
        return payload.decode("utf-8", errors="replace")[:limit], None
    if name.endswith(".doc"):
        raise AIServiceError("Formato DOC antiguo; conviértelo a DOCX o PDF para extraer texto.")
    raise AIServiceError(f"Formato no extraíble automáticamente: {artifact.mime_type}.")


def _video_metrics(payload: bytes, suffix: str, sample_count: int) -> tuple[dict[str, Any], list[str]]:
    source_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix or ".mp4", delete=False) as source:
            source.write(payload)
            source_path = Path(source.name)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        metadata = json.loads(probe.stdout)
        streams = metadata.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
        duration = float(metadata.get("format", {}).get("duration") or video.get("duration") or 0)
        frame_rate_raw = str(video.get("avg_frame_rate") or "0/1")
        numerator, denominator = (frame_rate_raw.split("/", 1) + ["1"])[:2]
        fps = float(numerator) / max(float(denominator), 1.0)
        metrics = {
            "duration_seconds": round(duration, 2),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": round(fps, 2),
            "video_codec": video.get("codec_name"),
            "has_audio": bool(audio),
            "audio_codec": audio.get("codec_name"),
            "audio_sample_rate": int(audio.get("sample_rate") or 0) if audio else None,
            "size_bytes": len(payload),
            "transcription_status": "NOT_CONFIGURED",
        }
        frames: list[str] = []
        with tempfile.TemporaryDirectory() as frame_dir:
            interval = max(duration / max(sample_count, 1), 1.0)
            pattern = str(Path(frame_dir) / "frame-%02d.jpg")
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(source_path), "-vf", f"fps=1/{interval},scale=640:-2", "-frames:v", str(sample_count), pattern],
                capture_output=True,
                timeout=120,
                check=True,
            )
            for frame in sorted(Path(frame_dir).glob("frame-*.jpg")):
                frames.append("data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode())
        metrics["sampled_frames"] = len(frames)
        return metrics, frames
    except (subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError) as error:
        raise AIServiceError(f"No se pudieron obtener métricas del video: {error}") from error
    finally:
        if source_path:
            source_path.unlink(missing_ok=True)


def _technical_record(db: Session, artifact: Artifact, modality: str) -> ArtifactTechnicalAnalysis:
    record = db.scalar(
        select(ArtifactTechnicalAnalysis).where(
            ArtifactTechnicalAnalysis.artifact_id == artifact.id
        )
    )
    if record is None:
        record = ArtifactTechnicalAnalysis(
            artifact_id=artifact.id,
            modality=modality,
            analysis_method="ffprobe+gpt4o-frames" if modality == "VIDEO" else "text-extraction+gpt4o",
        )
        db.add(record)
    record.modality = modality
    return record


def _persist_rubric_assessments(
    db: Session,
    case: CaseFile,
    raw: object,
    rubric_by_id: dict[str, RubricCriterion],
    valid_cm_ids: set[int],
    model_version: str,
) -> None:
    if not isinstance(raw, list):
        return
    valid_artifact_ids = {artifact.id for artifact in case.artifacts}
    for item in raw:
        if not isinstance(item, dict):
            continue
        criterion_id = str(item.get("criterion_id") or "")
        try:
            cm_id = int(item.get("cm_id"))
            level = max(1, min(4, int(item.get("level"))))
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            continue
        if criterion_id not in rubric_by_id or cm_id not in valid_cm_ids:
            continue
        assessment = db.scalar(
            select(RubricAssessment).where(
                RubricAssessment.case_id == case.id,
                RubricAssessment.cm_id == cm_id,
                RubricAssessment.criterion_id == criterion_id,
            )
        )
        if assessment is None:
            assessment = RubricAssessment(
                case_id=case.id,
                cm_id=cm_id,
                criterion_id=criterion_id,
                proposed_level=level,
                confidence=confidence,
                justification="",
            )
            db.add(assessment)
        assessment.proposed_level = level
        assessment.confidence = confidence
        assessment.justification = str(item.get("justification") or "Sin justificación")[:6000]
        evidence_ids = item.get("evidence_artifact_ids", [])
        assessment.evidence_artifact_ids = [
            str(value) for value in evidence_ids if str(value) in valid_artifact_ids
        ] if isinstance(evidence_ids, list) else []
        assessment.model_version = model_version
        if assessment.validation_status != "VALIDATED_BY_HUMAN":
            assessment.validation_status = "PENDING_HUMAN_REVIEW"


def _delivery_for_artifact(case: CaseFile, artifact_id: str):
    return next(
        (delivery for delivery in case.moodle_submissions if artifact_id in delivery.artifact_ids),
        None,
    )


def _normalise_findings(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        confidence = item.get("confidence", 0.5)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5
        cm_id = item.get("cm_id")
        try:
            cm_id = int(cm_id) if cm_id is not None else None
        except (TypeError, ValueError):
            cm_id = None
        artifact_ids = item.get("artifact_ids", [])
        findings.append(
            {
                "type": str(item.get("type") or "PEDAGOGICAL_PATTERN")[:80],
                "severity": str(item.get("severity") or "INFO").upper()[:20],
                "title": str(item.get("title") or "Hallazgo para revisión")[:240],
                "detail": str(item.get("detail") or "Sin detalle")[:4000],
                "cm_id": cm_id,
                "activity_name": str(item.get("activity_name") or "")[:255] or None,
                "artifact_ids": [str(value) for value in artifact_ids]
                if isinstance(artifact_ids, list)
                else [],
                "confidence": confidence,
                "score": _optional_score(item.get("score")),
                "similarity_score": _optional_score(item.get("similarity_score")),
                "validation_status": str(item.get("validation_status") or "")[:40] or None,
            }
        )
    return findings


def _optional_score(value: object) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _technical_findings(db: Session, case: CaseFile) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for delivery in case.moodle_submissions:
        if not delivery.artifact_ids:
            findings.append(
                {
                    "type": "MISSING_FILE",
                    "severity": "CRITICAL",
                    "title": "Entrega sin archivo",
                    "detail": "Moodle registra la entrega, pero no hay archivos asociados.",
                    "cm_id": delivery.cm_id,
                    "activity_name": delivery.activity_name,
                    "artifact_ids": [],
                    "confidence": 1.0,
                }
            )
    for artifact in case.artifacts:
        duplicates = list(
            db.scalars(
                select(Artifact).where(
                    Artifact.content_hash == artifact.content_hash,
                    Artifact.id != artifact.id,
                    Artifact.case_id != case.id,
                )
            )
        )
        if duplicates:
            delivery = _delivery_for_artifact(case, artifact.id)
            findings.append(
                {
                    "type": "EXACT_DUPLICATE",
                    "severity": "WARNING",
                    "title": "Archivo idéntico en otros expedientes",
                    "detail": f"El mismo contenido aparece en {len({item.case_id for item in duplicates})} expediente(s) adicional(es). Debe revisarse el contexto antes de concluir similitud indebida.",
                    "cm_id": delivery.cm_id if delivery else None,
                    "activity_name": delivery.activity_name if delivery else None,
                    "artifact_ids": [artifact.id],
                    "confidence": 1.0,
                }
            )
    return findings


def analyze_case(db: Session, settings: Settings, case_id: str, force: bool = False) -> CaseAIAnalysis:
    case = db.scalar(case_query().where(CaseFile.id == case_id))
    if not case:
        raise AIServiceError("Expediente no encontrado.")
    analysis = case.ai_analysis or CaseAIAnalysis(case_id=case.id)
    if case.ai_analysis is None:
        db.add(analysis)
    cm_ids = sorted({item.cm_id for item in case.moodle_submissions})
    criteria = list(
        db.scalars(
            select(ActivityReviewCriterion).where(
                ActivityReviewCriterion.course_id == case.course_id,
                ActivityReviewCriterion.cm_id.in_(cm_ids),
            )
        )
    )
    criteria_by_cmid = {item.cm_id: item for item in criteria}
    rubric_criteria = list(
        db.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.active.is_(True))
            .order_by(RubricCriterion.display_order)
        )
    )
    rubric_by_id = {item.id: item for item in rubric_criteria}
    missing_criteria = [cm_id for cm_id in cm_ids if cm_id not in criteria_by_cmid]
    if missing_criteria:
        analysis.status = "NEEDS_CONFIGURATION"
        analysis.error_message = (
            "Falta registrar la descripción y criterios de revisión para los CMID: "
            + ", ".join(map(str, missing_criteria))
        )
        analysis.findings = [
            {
                "type": "MISSING_REVIEW_CRITERIA",
                "severity": "CRITICAL",
                "title": "CMID sin ficha de revisión",
                "detail": f"Configura descripción, evidencia esperada y criterios para el CMID {cm_id}.",
                "cm_id": cm_id,
                "activity_name": None,
                "artifact_ids": [],
                "confidence": 1.0,
            }
            for cm_id in missing_criteria
        ]
        analysis.risk_level = "UNKNOWN"
        db.commit()
        db.refresh(analysis)
        return analysis
    if analysis.status == "COMPLETED" and not force:
        return analysis
    analysis.status = "PROCESSING"
    analysis.error_message = None
    case.status = CaseStatus.processing
    db.commit()

    documents: list[dict[str, Any]] = []
    video_frames: list[dict[str, Any]] = []
    technical = _technical_findings(db, case)
    for artifact in case.artifacts:
        delivery = _delivery_for_artifact(case, artifact.id)
        is_video = artifact.mime_type.startswith("video/") or artifact.filename.lower().endswith((".mp4", ".mov", ".webm"))
        record = _technical_record(db, artifact, "VIDEO" if is_video else "DOCUMENT")
        try:
            payload = _download_artifact(artifact, settings)
            if is_video:
                metrics, frames = _video_metrics(
                    payload, Path(artifact.filename).suffix, settings.ai_video_sample_frames
                )
                record.metrics = metrics
                record.status = "METRICS_EXTRACTED"
                record.error_message = None
                record.analyzed_at = datetime.now(UTC)
                artifact.duration_seconds = int(metrics.get("duration_seconds") or 0)
                documents.append(
                    {
                        "artifact_id": artifact.id,
                        "filename": artifact.filename,
                        "mime_type": artifact.mime_type,
                        "cm_id": delivery.cm_id if delivery else None,
                        "activity": delivery.activity_name if delivery else "Sin actividad asociada",
                        "video_metrics": metrics,
                        "analysis_scope": "Métricas técnicas y fotogramas; audio no transcrito.",
                    }
                )
                for index, frame in enumerate(frames):
                    if len(video_frames) >= 12:
                        break
                    video_frames.append(
                        {
                            "artifact_id": artifact.id,
                            "frame_index": index + 1,
                            "data_url": frame,
                        }
                    )
                artifact.processing_status = "VIDEO_SAMPLED"
                continue
            text, pages = _extract_text(artifact, payload, settings.ai_max_chars_per_file)
            if pages:
                artifact.page_count = pages
            if not text.strip():
                raise AIServiceError("El archivo no contiene texto extraíble; podría ser escaneado.")
            artifact.processing_status = "TEXT_EXTRACTED"
            words = text.split()
            record.metrics = {
                "size_bytes": len(payload),
                "page_count": pages,
                "character_count": len(text),
                "word_count": len(words),
                "extractable_text": True,
                "average_words_per_page": round(len(words) / pages, 2) if pages else None,
            }
            record.status = "METRICS_EXTRACTED"
            record.error_message = None
            record.analyzed_at = datetime.now(UTC)
            documents.append(
                {
                    "artifact_id": artifact.id,
                    "filename": artifact.filename,
                    "mime_type": artifact.mime_type,
                    "cm_id": delivery.cm_id if delivery else None,
                    "activity": delivery.activity_name if delivery else "Sin actividad asociada",
                    "text": text,
                }
            )
        except (AIServiceError, ValueError, OSError) as error:
            artifact.processing_status = "NEEDS_REVIEW"
            artifact.extracted_summary = str(error)
            record.status = "NEEDS_REVIEW"
            record.error_message = str(error)
            record.analyzed_at = datetime.now(UTC)
            technical.append(
                {
                    "type": "UNREADABLE_OR_UNSUPPORTED",
                    "severity": "WARNING",
                    "title": "Contenido no analizado",
                    "detail": f"{artifact.filename}: {error}",
                    "cm_id": delivery.cm_id if delivery else None,
                    "activity_name": delivery.activity_name if delivery else None,
                    "artifact_ids": [artifact.id],
                    "confidence": 1.0,
                }
            )
    text_documents = [item for item in documents if item.get("text")]
    for index, left in enumerate(text_documents):
        for right in text_documents[index + 1 :]:
            if left.get("cm_id") == right.get("cm_id"):
                continue
            similarity = SequenceMatcher(
                None, str(left["text"])[:10000], str(right["text"])[:10000]
            ).ratio() * 100
            if similarity >= 75:
                technical.append(
                    {
                        "type": "POSSIBLE_SIMILARITY",
                        "severity": "WARNING",
                        "title": "Alta similitud entre documentos de distintos CMID",
                        "detail": f"Coincidencia textual aproximada de {similarity:.1f}%. Verifique si la repetición es coherente con la secuencia.",
                        "cm_id": right.get("cm_id"),
                        "activity_name": right.get("activity"),
                        "artifact_ids": [left["artifact_id"], right["artifact_id"]],
                        "confidence": 0.9,
                        "similarity_score": round(similarity, 1),
                    }
                )
    db.commit()

    try:
        ai_result = _azure_json(
            settings,
            [
                {
                    "role": "system",
                    "content": (
                        "Eres analista pedagógico de DIFODS. Analiza solo la evidencia entregada, sin calificar al docente ni inferir datos ausentes. "
                        "Aplica métricas diferenciadas: en PDF/DOCX revisa contenido, estructura, extensión y correspondencia textual; en video usa duración, resolución, presencia de audio y los fotogramas muestreados. No afirmes nada sobre el audio porque no fue transcrito. "
                        "Evalúa cada CMID únicamente contra su ficha de revisión. Devuelve JSON con summary, cluster_label, risk_level, document_summaries y findings. "
                        "Debe existir un finding type=CMID_REVIEW por cada CMID con score 0..100, similarity_score 0..100, validation_status (CONFORME|PARCIAL|NO_CONFORME), title, detail, cm_id, activity_name, artifact_ids y confidence. "
                        "Añade un finding type=CROSS_CMID_COHERENCE con score 0..100 que determine si la secuencia entre los CMID es lógica, consistente y se refiere al mismo proceso pedagógico. "
                        "Añade alertas CONTENT_MISMATCH, INCOMPLETE_EVIDENCE, PEDAGOGICAL_PATTERN o POSSIBLE_SIMILARITY cuando correspondan. "
                        "Además devuelve rubric_assessments: exactamente una valoración por cada combinación CMID y criterio de rúbrica. Cada elemento incluye cm_id, criterion_id, level 1..4, confidence 0..1, justification y evidence_artifact_ids. Si no hay evidencia suficiente usa nivel 1 con baja confianza y explícalo; no inventes evidencia. "
                        "No declares plagio; una similitud solo es una señal para revisión humana."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                            "docente": case.teacher_code,
                            "curso": case.course_name,
                            "entregas": [
                                {
                                    "cm_id": item.cm_id,
                                    "actividad": item.activity_name,
                                    "estado": item.status,
                                    "archivos": item.artifact_ids,
                                    "ficha_revision": {
                                        "descripcion": criteria_by_cmid[item.cm_id].description,
                                        "evidencia_esperada": criteria_by_cmid[item.cm_id].expected_evidence,
                                        "criterios": criteria_by_cmid[item.cm_id].review_criteria,
                                    },
                                }
                                for item in case.moodle_submissions
                            ],
                            "documentos": documents,
                            "rubrica_mbddl": [
                                {
                                    "criterion_id": item.id,
                                    "dimension": item.dimension,
                                    "criterio": item.criterion,
                                    "nivel_4": item.level_4,
                                    "nivel_3": item.level_3,
                                    "nivel_2": item.level_2,
                                    "nivel_1": item.level_1,
                                }
                                for item in rubric_criteria
                            ],
                            }, ensure_ascii=False),
                        },
                        *[
                            {
                                "type": "text",
                                "text": f"Fotograma {frame['frame_index']} del archivo {frame['artifact_id']}",
                            }
                            for frame in video_frames
                        ],
                        *[
                            {
                                "type": "image_url",
                                "image_url": {"url": frame["data_url"], "detail": "low"},
                            }
                            for frame in video_frames
                        ],
                    ],
                },
            ],
        )
        summaries = ai_result.get("document_summaries", {})
        for artifact in case.artifacts:
            if artifact.id in summaries:
                artifact.extracted_summary = str(summaries[artifact.id])[:4000]
                artifact.processing_status = "ANALYZED"
        ai_findings = _normalise_findings(ai_result.get("findings", []))
        _persist_rubric_assessments(
            db,
            case,
            ai_result.get("rubric_assessments", []),
            rubric_by_id,
            set(cm_ids),
            settings.azure_openai_deployment,
        )
        analysis.findings = [*technical, *ai_findings]
        analysis.summary = str(ai_result.get("summary") or "Análisis completado.")
        analysis.cluster_label = str(ai_result.get("cluster_label") or "Sin clúster")[:160]
        risk = str(ai_result.get("risk_level") or "LOW").upper()
        analysis.risk_level = risk if risk in {"LOW", "MEDIUM", "HIGH"} else "LOW"
        analysis.model_version = settings.azure_openai_deployment
        analysis.status = "COMPLETED"
        analysis.analyzed_at = datetime.now(UTC)
        case.executive_summary = analysis.summary
        case.status = CaseStatus.ready
    except AIServiceError as error:
        analysis.status = "FAILED"
        analysis.error_message = str(error)
        analysis.findings = technical
        case.status = CaseStatus.failed
        db.commit()
        raise
    db.commit()
    db.refresh(analysis)
    return analysis


def answer_case_question(db: Session, settings: Settings, case: CaseFile, question: str) -> tuple[str, list[dict[str, str]]]:
    sources = [
        {
            "artifact_id": artifact.id,
            "filename": artifact.filename,
            "excerpt": (artifact.extracted_summary or "")[:500],
        }
        for artifact in case.artifacts
        if artifact.extracted_summary
    ]
    if not sources and not case.executive_summary:
        raise AIServiceError("Primero ejecuta el análisis IA del expediente para preparar sus evidencias.")
    result = _azure_json(
        settings,
        [
            {
                "role": "system",
                "content": "Responde en español únicamente con la información del expediente. No califiques al docente. Si no existe evidencia suficiente, dilo expresamente. Devuelve JSON con answer.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "pregunta": question,
                        "resumen": case.executive_summary,
                        "hallazgos": case.ai_analysis.findings if case.ai_analysis else [],
                        "fuentes": sources,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )
    return str(result.get("answer") or "No se obtuvo una respuesta."), sources


def aggregate_analysis(analyses: list[CaseAIAnalysis]) -> dict[str, Any]:
    clusters = Counter(item.cluster_label or "Sin clúster" for item in analyses if item.status == "COMPLETED")
    finding_types: Counter[str] = Counter()
    critical = warning = 0
    for analysis in analyses:
        for finding in analysis.findings or []:
            finding_types[str(finding.get("type", "OTHER"))] += 1
            severity = str(finding.get("severity", "INFO")).upper()
            critical += severity == "CRITICAL"
            warning += severity == "WARNING"
    return {
        "analyzed_cases": sum(item.status == "COMPLETED" for item in analyses),
        "critical_findings": critical,
        "warning_findings": warning,
        "clusters": [{"label": key, "count": value} for key, value in clusters.most_common()],
        "finding_types": [{"type": key, "count": value} for key, value in finding_types.most_common()],
    }
