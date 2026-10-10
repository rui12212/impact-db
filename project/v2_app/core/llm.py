from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from v2_app.core.config import OPENAI_API_KEY, OPENAI_LLM_MODEL

log = logging.getLogger("impactdb.v2")

_client: Optional[AsyncOpenAI] = None

# 対話中に呼ぶので長く待たせない
TIMEOUT_SECONDS = 30

# 推論モデル（gpt-5系・o系）の制約。2026-10-10 に実機で確認
#   - temperature は既定(1)以外を受けない → 送らない
#   - max_tokens は使えない → max_completion_tokens
#   - 推論トークンが先に予算を食うので、小さい上限だと本文が空になる
#     （max_completion_tokens=120 で出力0文字・finish_reason="length"）
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

# 推論モデルに渡す下限。これ未満だと空文字が返る危険がある
MIN_COMPLETION_TOKENS = 1500

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


def _is_reasoning(model: str) -> bool:
    return model.startswith(REASONING_PREFIXES)


def _limits(
    model: str, max_tokens: Optional[int], temperature: Optional[float]
) -> Dict[str, Any]:
    """モデルに応じて上限と temperature を組み立てる。

    推論モデルでは temperature を送らず、上限は max_completion_tokens。
    呼び出し側が小さい値を渡しても MIN_COMPLETION_TOKENS まで引き上げる
    （推論トークンに食われて本文が空になるのを防ぐ）。
    """
    if _is_reasoning(model):
        if max_tokens is None:
            return {}
        return {"max_completion_tokens": max(max_tokens, MIN_COMPLETION_TOKENS)}

    kwargs: Dict[str, Any] = {}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


@retry(**_RETRY)
async def complete_text(
    system: str,
    user: str,
    *,
    max_tokens: Optional[int] = 600,
    temperature: Optional[float] = 0.4,
    model: Optional[str] = None,
) -> str:
    """ふつうの文章生成。問いかけ・見出し・要約で使う。"""
    name = model or OPENAI_LLM_MODEL
    res = await get_client().chat.completions.create(
        model=name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **_limits(name, max_tokens, temperature),
    )
    choice = res.choices[0]
    text = (choice.message.content or "").strip()

    if not text:
        # 推論トークンに食われて本文が出なかった場合はここに来る
        log.warning("空の応答 model=%s finish=%s", name, choice.finish_reason)
    return text


@retry(**_RETRY)
async def complete_json(
    system: str,
    user: str,
    schema: Dict[str, Any],
    *,
    schema_name: str = "result",
    temperature: Optional[float] = 0.0,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """JSONで受け取る。値の抽出・分類で使う。

    上限は送らない。JSONスキーマで出力が縛られているので切り詰める
    意味がなく、途中で切れると JSONDecodeError になるだけ。
    """
    name = model or OPENAI_LLM_MODEL
    res = await get_client().chat.completions.create(
        model=name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        },
        **_limits(name, None, temperature),
    )
    content = res.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        log.warning("JSONとして読めない応答 model=%s", name)
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
