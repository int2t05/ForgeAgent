"""记忆域：会话内消息的持久化与检索。

当前由 ``app.repositories.message_repository`` 与任务用例编排；此处保留包作为
向量记忆、摘要策略等扩展挂载点，避免与 ORM 层循环依赖。
"""
