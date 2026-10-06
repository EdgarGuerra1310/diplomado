from celery import Celery

from app.ai_analysis import analyze_case
from app.config import get_settings
from app.database import SessionLocal

settings = get_settings()
celery_app = Celery("difods_copilot", broker=settings.celery_broker_url, backend=settings.redis_url)
celery_app.conf.task_routes = {"app.worker.process_submission": {"queue": "ingestion"}}


@celery_app.task(
    name="app.worker.process_submission",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def process_submission(case_id: str, force: bool = False) -> dict[str, str]:
    """Punto de extensión para descarga, OCR, transcripción y análisis real."""
    db = SessionLocal()
    try:
        result = analyze_case(db, settings, case_id, force=force)
        return {"case_id": case_id, "status": result.status}
    finally:
        db.close()
