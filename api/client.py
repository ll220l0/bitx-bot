import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


async def send_lead_to_api(payload: dict[str, Any]) -> bool:
    try:
        async with httpx.AsyncClient(timeout=7.0) as client:
            response = await client.post(f"{settings.API_BASE}/leads/", json=payload)
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("Failed to send lead to API")
        return False
