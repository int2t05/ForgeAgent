"""烟测：直接调用 ``plan_steps_with_llm``（需已配置 OPENAI_API_KEY 等）。

从任意目录运行均可：脚本会把进程 cwd 切到仓库根以加载根目录 ``.env``。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent


def _bootstrap() -> None:
    sys.path.insert(0, str(_BACKEND))
    import os

    os.chdir(_REPO)


async def _run() -> int:
    _bootstrap()

    from app.agent.llm_client import is_llm_configured, plan_steps_with_llm
    from app.config import get_settings

    settings = get_settings()
    if not is_llm_configured(settings):
        print("未检测到 OPENAI_API_KEY（或为空），跳过真实调用。", file=sys.stderr)
        return 2

    user_message = (
        "帮我写一个 Python 脚本把 CSV 转成 JSON，并列出需要注意的边界情况。"
    )
    print("model:", settings.openai_model or "(default)")
    print("base:", (settings.openai_api_base or "").strip() or "(default OpenAI)")
    print("user_message:", user_message)
    print("---")

    steps = await plan_steps_with_llm(user_message, settings)
    print(json.dumps(steps, ensure_ascii=False, indent=2))
    print("---")
    print("ok, step count:", len(steps))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
