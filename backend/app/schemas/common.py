"""跨资源通用响应模型。"""

from pydantic import BaseModel


class OperationOkResponse(BaseModel):
    """删除、清理类操作成功时的统一响应体。"""

    ok: bool = True
