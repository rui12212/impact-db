from __future__ import annotations

from typing import Any, Optional

from notion_client import AsyncClient
from notion_client.errors import APIErrorCode, APIResponseError, RequestTimeoutError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from v2_app.core.config import NOTION_API_KEY


_client: Optional[AsyncClient] = None

# Notion API は 3リクエスト/秒（インテグレーション全体で共有）
RETRYABLE_CODES = {
    APIErrorCode.RateLimited,
    APIErrorCode.ConflictError,
    APIErrorCode.InternalServerError,
    APIErrorCode.ServiceUnavailable,
}

def get_notion() -> AsyncClient:
    global _client
    if _client is None:
        if not NOTION_API_KEY:
            raise RuntimeError("NOTION_API_KEYが設定されていないです")
        _client = AsyncClient(auth=NOTION_API_KEY)
    return _client

def _is_retryable(e: BaseException) -> bool:
    if isinstance(e, RequestTimeoutError):
        return True
    if isinstance(e, APIResponseError):
        return e.code in RETRYABLE_CODES
    return False

notion_retry = retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)

@notion_retry
async def create_page(database_id: str, properties: dict, **kwargs: Any) -> dict:
    return await get_notion().pages.create(
        parent={"database_id": database_id}, properties=properties, **kwargs
    )

@notion_retry
async def update_page(page_id: str, properties: dict) -> dict:
    return await get_notion().pages.update(page_id=page_id, properties=properties)


@notion_retry
async def query_database(database_id: str, **kwargs: Any) -> dict:
    return await get_notion().databases.query(database_id=database_id, **kwargs)

@notion_retry
async def retrieve_page(page_id: str) -> dict:
    return await get_notion().pages.retrieve(page_id=page_id)