import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Artifact,
    CaseFile,
    CaseStatus,
    Citation,
    IndicatorResult,
    Measurement,
    RubricAssessment,
)


def case_query():
    return select(CaseFile).options(
        selectinload(CaseFile.artifacts),
        selectinload(CaseFile.artifacts).selectinload(Artifact.technical_analysis),
        selectinload(CaseFile.identity),
        selectinload(CaseFile.moodle_submissions),
        selectinload(CaseFile.ai_analysis),
        selectinload(CaseFile.rubric_assessments).selectinload(
            RubricAssessment.criterion_ref
        ),
        selectinload(CaseFile.indicators).selectinload(IndicatorResult.citations),
        selectinload(CaseFile.indicators).selectinload(IndicatorResult.reviews),
    )


def seed_demo_case(db: Session) -> CaseFile:
    existing = db.scalar(select(CaseFile).where(CaseFile.submission_id == 2026001))
    if existing:
        return db.scalar(case_query().where(CaseFile.id == existing.id))

    case = CaseFile(
        teacher_code="DOC-LB-0001",
        teacher_display_name="Docente demostrativo",
        course_id=2741,
        course_name="Diplomado en metodologías activas 2026",
        submission_id=2026001,
        manifest_version=1,
        measurement=Measurement.baseline,
        status=CaseStatus.ready,
        region="Lima Metropolitana",
        ugel="UGEL 03",
        education_level="Secundaria",
        executive_summary=(
            "La IA localizó señales de participación activa, preguntas abiertas y evaluación "
            "formativa. Estas señales no constituyen una evaluación y deben ser verificadas "
            "por el especialista en las fuentes citadas."
        ),
    )
    db.add(case)
    db.flush()

    artifacts = [
        Artifact(
            case_id=case.id,
            evidence_type="UNIDAD_DIDACTICA",
            filename="unidad_didactica.pdf",
            mime_type="application/pdf",
            content_hash=hashlib.sha256(b"ud").hexdigest(),
            page_count=12,
            processing_status="PROCESSED",
            extracted_summary="Unidad centrada en comprensión lectora y deliberación.",
        ),
        Artifact(
            case_id=case.id,
            evidence_type="SESION_PRIORIZADA",
            filename="sesion_priorizada.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content_hash=hashlib.sha256(b"sp").hexdigest(),
            page_count=6,
            processing_status="PROCESSED",
            extracted_summary="Sesión con lectura, discusión guiada y producción argumentativa.",
        ),
        Artifact(
            case_id=case.id,
            evidence_type="VIDEO_CLASE",
            filename="video_clase.mp4",
            mime_type="video/mp4",
            content_hash=hashlib.sha256(b"video").hexdigest(),
            duration_seconds=548,
            processing_status="PROCESSED",
            extracted_summary="Se identificaron preguntas, intercambio grupal y retroalimentación.",
        ),
        Artifact(
            case_id=case.id,
            evidence_type="NARRACION_REFLEXIVA",
            filename="narracion_reflexiva.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content_hash=hashlib.sha256(b"nr").hexdigest(),
            page_count=5,
            processing_status="PROCESSED",
            extracted_summary="La docente cuestiona el tiempo otorgado a la argumentación.",
        ),
        Artifact(
            case_id=case.id,
            evidence_type="TRABAJOS_ESTUDIANTES",
            filename="productos_estudiantes.pdf",
            mime_type="application/pdf",
            content_hash=hashlib.sha256(b"te").hexdigest(),
            page_count=9,
            processing_status="PROCESSED",
            extracted_summary="Tres productos con evidencias y retroalimentaciones escritas.",
        ),
    ]
    db.add_all(artifacts)
    db.flush()

    indicators = [
        IndicatorResult(
            case_id=case.id,
            code="PC_PREGUNTA_ABIERTA",
            dimension="Pensamiento crítico",
            label="Formula preguntas abiertas",
            status="EVIDENCE_FOUND",
            confidence=0.86,
            explanation="Se localizó una pregunta que solicita justificar una posición con evidencia textual.",
        ),
        IndicatorResult(
            case_id=case.id,
            code="EF_RETROALIMENTACION",
            dimension="Evaluación formativa",
            label="Ofrece retroalimentación orientada a la mejora",
            status="POSSIBLE_EVIDENCE",
            confidence=0.74,
            explanation="El segmento contiene una indicación para revisar la evidencia y reformular la respuesta.",
        ),
        IndicatorResult(
            case_id=case.id,
            code="RD_AUTOCRITICA",
            dimension="Reflexión docente",
            label="Reconoce una decisión que modificaría",
            status="EVIDENCE_FOUND",
            confidence=0.82,
            explanation="La narración identifica una limitación temporal y propone una acción concreta.",
        ),
    ]
    db.add_all(indicators)
    db.flush()

    db.add_all(
        [
            Citation(
                indicator_id=indicators[0].id,
                artifact_id=artifacts[2].id,
                quote="¿Qué parte del texto respalda su posición y por qué?",
                start_seconds=271,
                end_seconds=289,
            ),
            Citation(
                indicator_id=indicators[1].id,
                artifact_id=artifacts[2].id,
                quote="Vuelve a la evidencia que elegiste y explícame qué cambiarías.",
                start_seconds=423,
                end_seconds=447,
            ),
            Citation(
                indicator_id=indicators[2].id,
                artifact_id=artifacts[3].id,
                quote="Debí reservar más tiempo para contrastar los argumentos de los grupos.",
                page=4,
                paragraph=3,
            ),
        ]
    )
    db.commit()
    return db.scalar(case_query().where(CaseFile.id == case.id))


def grounded_demo_answer(case: CaseFile, question: str) -> tuple[str, list[Citation]]:
    terms = set(question.lower().split())
    ranked: list[tuple[int, IndicatorResult]] = []
    for indicator in case.indicators:
        haystack = f"{indicator.label} {indicator.dimension} {indicator.explanation}".lower()
        score = sum(1 for term in terms if len(term) > 3 and term in haystack)
        ranked.append((score, indicator))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [item[1] for item in ranked[:2] if item[0] > 0] or [item[1] for item in ranked[:1]]
    citations = [citation for indicator in selected for citation in indicator.citations]
    signals = "; ".join(indicator.explanation for indicator in selected)
    return f"Encontré las siguientes señales para revisión: {signals}", citations
