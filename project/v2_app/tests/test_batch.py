"""バッチの危ない分岐。通信なし（偽のクライアントを渡す）。

keyword_cleanup は **選択肢を消す**処理で、毎晩無人で走る。
消しすぎると既存レコードのタグが外れ、戻す手段が無い。
ここだけはテストで止める。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from v2_app.batch import keyword_cleanup as kc
from v2_app.tests.harness import Suite

suite = Suite("batch")


class _Res:
    def __init__(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 300:
            raise RuntimeError(self.text)


class _FakeClient:
    """Notion の代わり。options と「使われている値」を指定して渡す。"""

    def __init__(self, options: List[dict], used: List[List[str]]) -> None:
        self.options = options
        self.used = used
        self.patched: List[dict] = []

    async def get(self, url: str) -> _Res:
        if "/databases/" in url:
            return _Res({"data_sources": [{"id": "ds-1"}]})
        return _Res(
            {"properties": {"Keywords": {"multi_select": {"options": self.options}}}}
        )

    async def post(self, url: str, json: Dict[str, Any]) -> _Res:  # noqa: A002
        rows = [
            {
                "properties": {
                    "Keywords": {"multi_select": [{"name": n} for n in names]}
                }
            }
            for names in self.used
        ]
        return _Res({"results": rows, "has_more": False})

    async def patch(self, url: str, json: Dict[str, Any]) -> _Res:  # noqa: A002
        self.patched.append(json)
        # 書き換え後の読み直しに備えて options を更新する
        self.options = json["properties"]["Keywords"]["multi_select"]["options"]
        return _Res({"ok": True})


OPTIONS = [
    {"id": "a", "name": "ក្រុម", "color": "default"},
    {"id": "b", "name": "ចំណេះដឹង", "color": "blue"},
    {"id": "c", "name": "使われていない語", "color": "red"},
]


def _run(client: _FakeClient, *, dry_run: bool = False) -> Dict[str, Any]:
    return asyncio.run(
        kc.prune_one(client, "db-1", "Keywords", dry_run=dry_run)
    )


@suite.case("使われていない選択肢だけ消す")
def _() -> None:
    client = _FakeClient(list(OPTIONS), [["ក្រុម"], ["ចំណេះដឹង"]])
    out = _run(client)
    assert out["removed"] == 1, out
    assert out["kept"] == 2, out
    assert out["names"] == ["使われていない語"], out


@suite.case("残す選択肢は id ごと渡す（タグが外れないように）")
def _() -> None:
    """⚠️ 名前だけ渡すと Notion が別の選択肢として作り直し、
    既にレコードに付いているタグが外れる。
    """
    client = _FakeClient(list(OPTIONS), [["ក្រុម"], ["ចំណេះដឹង"]])
    _run(client)
    sent = client.patched[0]["properties"]["Keywords"]["multi_select"]["options"]
    assert [o["id"] for o in sent] == ["a", "b"], sent
    assert all("name" in o and "color" in o for o in sent), sent


@suite.case("1件も使われていなければ何もしない（全消去を防ぐ安全装置）")
def _() -> None:
    """⚠️ ここを素通りさせると全選択肢の削除になる。

    毎晩無人で走るので、Notionの障害でクエリが空を返した時に
    既存レコードのタグが全部外れる。
    """
    client = _FakeClient(list(OPTIONS), [])
    out = _run(client)
    assert out.get("skipped") is True, out
    assert out["removed"] == 0, out
    assert not client.patched, "書き込んではいけない"


@suite.case("消すものが無ければ書き込まない")
def _() -> None:
    used = [["ក្រុម"], ["ចំណេះដឹង"], ["使われていない語"]]
    client = _FakeClient(list(OPTIONS), used)
    out = _run(client)
    assert out["removed"] == 0, out
    assert not client.patched, "変化が無いのに書き込んでいる"


@suite.case("--dry-run では書き込まない")
def _() -> None:
    client = _FakeClient(list(OPTIONS), [["ក្រុម"]])
    out = _run(client, dry_run=True)
    assert out["removed"] == 2, out
    assert not client.patched, "dry-run なのに書き込んでいる"
