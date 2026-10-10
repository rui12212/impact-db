"""オフライン＋Redis のテストをまとめて実行する。

    docker compose -f docker/v2.local.yml exec app python -m v2_app.tests

OpenAI / Notion / R2 を実際に叩くものは含めない。
それは v2_app.tests.smoke_external で明示的に実行する。
"""

from __future__ import annotations

import sys

from v2_app.tests import (
    test_config,
    test_flow,
    test_media,
    test_prompts,
    test_reflection,
    test_registry,
    test_schemas,
    test_session,
)
from v2_app.tests.harness import report

SUITES = [
    test_config.suite,
    test_flow.suite,
    test_media.suite,
    test_prompts.suite,
    test_reflection.suite,
    test_registry.suite,
    test_schemas.suite,
    test_session.suite,
]


def main() -> int:
    return report([s.run() for s in SUITES])


if __name__ == "__main__":
    sys.exit(main())
