"""HTTP 层统一异常与错误体（契约见 docs/api/API.md 错误响应约定）。"""

from typing import Any

from fastapi import HTTPException, status


class AppHTTPException(HTTPException):
    """业务/资源类错误：可选机器可读 code，响应体为 { detail, code? }。"""

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> None:
        """构造符合 OpenAPI 错误约定的 HTTP 异常体。"""
        body: dict[str, Any] = {"detail": detail}
        if code is not None:
            body["code"] = code
        super().__init__(status_code=status_code, detail=body, headers=headers)
