from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from v2_app.core.config import OPENAI_API_KEY, OPENAI_LLM_MODEL

_client: Optional[AsyncOpenAI] = None

# 対話中に呼ぶので長く待たせない
TIMEOUT_SECONDS = 30

_RETRY = dict(
    retry=retry_if_exception_type(
        (RateLimitError, APIConnectionError, APITimeoutError)
    ),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY が設定されていません")
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=TIMEOUT_SECONDS)
    return _client


@retry(**_RETRY)
async def complete_text(
    system: str,
    user: str,
    *,
    max_tokens: int = 300,
    temperature: float = 0.4,
    model: Optional[str] = None,
) -> str:
    """ふつうの文章生成。問いかけ・見出し・要約で使う。"""
    res = await get_client().chat.completions.create(
        model=model or OPENAI_LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (res.choices[0].message.content or "").strip()


@retry(**_RETRY)
async def complete_json(
    system: str,
    user: str,
    schema: Dict[str, Any],
    *,
    schema_name: str = "result",
    temperature: float = 0.0,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """JSONで受け取る。値の抽出・分類で使う。"""
    res = await get_client().chat.completions.create(
        model=model or OPENAI_LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        },
    )
    content = res.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def build_object_schema(keys: List[str]) -> Dict[str, Any]:
    """「このキーのうち分かるものだけ埋めて」という形のスキーマを作る。

    strict モードは全キーを required にする必要があるため、
    型を [string, null] にして「分からない = null」を表現する。
    """
    return {
        "type": "object",
        "properties": {k: {"type": ["string", "null"]} for k in keys},
        "required": keys,
        "additionalProperties": False,
    }
