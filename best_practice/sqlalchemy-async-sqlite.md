# SQLAlchemy 2.0 异步 + SQLite（aiosqlite）要点

简洁伪代码，便于后续阶段扩展（连接池、迁移、读写分离等）。

## 1. 引擎与会话工厂

```text
url = "sqlite+aiosqlite:///./app.db"
engine = create_async_engine(url)
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

- 单元测试内存库建议 `poolclass=StaticPool`，避免 `:memory:` 每连接一座空库。

## 2. 建表（MVP）

```text
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

- 生产演进可改为 Alembic；启动 `create_all` 仅适合 MVP。

## 3. SQLite 外键

```text
on_engine_connect:
  PRAGMA foreign_keys=ON
```

- 每个新连接执行一次；勿依赖单次手动 `exec_driver_sql`。

## 4. FastAPI 注入

```text
async def get_db():
  async with SessionFactory() as session:
    try:
      yield session
      await session.commit()
    except:
      await session.rollback()
      raise
```

## 5. 同一 task 内 seq 单调递增（事务内）

```text
async with session.begin():  # 或与 get_db 同一事务边界
  max_seq = SELECT coalesce(max(seq),0) FROM task_events WHERE task_id = ?
  INSERT INTO task_events (task_id, seq, ...) VALUES (?, max_seq+1, ...)
  # 表级 UNIQUE(task_id, seq) 兜住竞态双插
```

- 高并发同一 task 时可评估 `BEGIN IMMEDIATE` 或与业务队列串行化。
