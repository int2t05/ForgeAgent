"""backend/tests 根 conftest：在任意测试 import app 之前固定 DATABASE_URL。"""

import os
from pathlib import Path

_root = Path(__file__).resolve().parent
_db_file = _root / "test_runtime.sqlite"
os.environ["DATABASE_URL"] = (
    "sqlite+aiosqlite:///" + _db_file.as_posix().replace(chr(92), "/")
)
