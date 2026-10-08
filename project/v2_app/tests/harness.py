"""依存ライブラリなしの最小テストハーネス。

pytest を入れていないので、同じことを自分でやる。
使い方:

    from v2_app.tests.harness import Suite

    s = Suite("flow")

    @s.case("必須が埋まっていなければ未完了")
    def _():
        assert not flow.is_complete(FIELDS, {})

    s.run()   # -> (passed, failed)
"""

from __future__ import annotations

import asyncio
import inspect
import traceback
from typing import Callable, List, Tuple

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


class Suite:
    def __init__(self, name: str) -> None:
        self.name = name
        self.cases: List[Tuple[str, Callable]] = []

    def case(self, title: str) -> Callable:
        def deco(fn: Callable) -> Callable:
            self.cases.append((title, fn))
            return fn

        return deco

    def run(self) -> Tuple[int, int]:
        print(f"\n{DIM}--- {self.name} ---{RESET}")
        passed = failed = 0
        for title, fn in self.cases:
            try:
                result = fn()
                if inspect.isawaitable(result):
                    asyncio.run(_await(result))
            except Exception:
                failed += 1
                print(f"{RED}NG{RESET} {title}")
                for line in traceback.format_exc().strip().splitlines()[-3:]:
                    print(f"     {DIM}{line.strip()}{RESET}")
            else:
                passed += 1
                print(f"{GREEN}OK{RESET} {title}")
        return passed, failed


async def _await(awaitable):
    return await awaitable


def report(results: List[Tuple[int, int]]) -> int:
    """終了コードを返す。すべて通れば 0。"""
    passed = sum(p for p, _ in results)
    failed = sum(f for _, f in results)
    print()
    if failed:
        print(f"{RED}{failed} 件失敗{RESET} / {passed + failed} 件")
        return 1
    print(f"{GREEN}全 {passed} 件 OK{RESET}")
    return 0
