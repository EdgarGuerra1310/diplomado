import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_analysis import _download_artifact, _extract_text
from app.config import Settings
from app.models import Artifact, ArtifactText

TEXT_LIMIT = 60000


def is_video(artifact: Artifact) -> bool:
    return artifact.mime_type.startswith("video/") or artifact.filename.lower().endswith(
        (".mp4", ".mov", ".webm")
    )


def _extract(artifact: Artifact, settings: Settings) -> tuple[str, str, str | None]:
    last_error = ""
    for attempt in range(5):
        try:
            payload = _download_artifact(artifact, settings)
            text, _ = _extract_text(artifact, payload, TEXT_LIMIT)
            return artifact.id, ("EXTRACTED" if text.strip() else "EMPTY"), text
        except Exception as error:  # noqa: BLE001 - cualquier fallo se registra por archivo
            last_error = str(error)[:500]
            if "No se pudo descargar" not in last_error:
                break
            time.sleep(1.5 * (attempt + 1))
    return artifact.id, "FAILED", last_error


def prepare_texts(
    db: Session,
    settings: Settings,
    case_ids: list[str],
    batch_size: int = 8,
    retry_failed: bool = False,
) -> dict[str, int]:
    artifacts = [
        item
        for item in db.scalars(select(Artifact).where(Artifact.case_id.in_(case_ids)))
        if not is_video(item)
    ]
    if retry_failed:
        for row in db.scalars(
            select(ArtifactText).where(
                ArtifactText.artifact_id.in_([a.id for a in artifacts]),
                ArtifactText.status == "FAILED",
            )
        ):
            db.delete(row)
        db.commit()
    existing = {
        item.artifact_id: item
        for item in db.scalars(
            select(ArtifactText).where(ArtifactText.artifact_id.in_([a.id for a in artifacts]))
        )
    }
    pending = [item for item in artifacts if item.id not in existing]
    batch = pending[:batch_size]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda item: _extract(item, settings), batch))
    for artifact_id, status, payload in results:
        row = existing.get(artifact_id) or ArtifactText(artifact_id=artifact_id)
        row.status = status
        row.text = payload if status in {"EXTRACTED", "EMPTY"} else None
        row.char_count = len(payload) if status in {"EXTRACTED", "EMPTY"} and payload else 0
        row.error_message = payload if status == "FAILED" else None
        db.add(row)
    db.commit()
    statuses = [
        item.status
        for item in db.scalars(
            select(ArtifactText).where(ArtifactText.artifact_id.in_([a.id for a in artifacts]))
        )
    ]
    return {
        "total": len(artifacts),
        "ready": statuses.count("EXTRACTED"),
        "empty": statuses.count("EMPTY"),
        "failed": statuses.count("FAILED"),
        "pending": len(artifacts) - len(statuses),
        "processed": len(batch),
    }
