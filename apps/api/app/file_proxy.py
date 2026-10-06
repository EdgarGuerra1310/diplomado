from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.models import Artifact


async def stream_artifact(
    artifact: Artifact,
    settings: Settings,
    range_header: str | None = None,
) -> StreamingResponse:
    if not artifact.source_url:
        raise HTTPException(
            status_code=404, detail="El archivo no tiene una URL Moodle disponible."
        )
    source = urlparse(artifact.source_url)
    allowed = urlparse(settings.moodle_base_url)
    if source.scheme != "https" or source.hostname != allowed.hostname:
        raise HTTPException(
            status_code=400, detail="La URL del archivo no pertenece al Moodle autorizado."
        )

    headers = {"Range": range_header} if range_header else {}
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.moodle_timeout_seconds, connect=15),
        follow_redirects=True,
    )
    request = client.build_request(
        "GET",
        artifact.source_url,
        params={"token": settings.moodle_token},
        headers=headers,
    )
    try:
        upstream = await client.send(request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(
            status_code=502, detail=f"No se pudo abrir el archivo Moodle: {error}"
        ) from error
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Moodle no permitió abrir el archivo (HTTP {upstream.status_code}).",
        )

    async def chunks() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    passthrough = {}
    for header in ("content-length", "content-range", "accept-ranges", "last-modified"):
        if value := upstream.headers.get(header):
            passthrough[header] = value
    safe_filename = artifact.filename.replace('"', "")
    passthrough["Content-Disposition"] = f'inline; filename="{safe_filename}"'
    return StreamingResponse(
        chunks(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type") or artifact.mime_type,
        headers=passthrough,
    )
