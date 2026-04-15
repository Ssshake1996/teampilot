from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.utils.security import decode_token
from app.websocket.manager import manager


async def drop_legacy_user_email_column(conn) -> None:
    from sqlalchemy import inspect, text

    def get_legacy_user_columns(sync_conn) -> tuple[bool, bool]:
        inspector = inspect(sync_conn)
        if not inspector.has_table("users"):
            return False, False
        columns = {col["name"] for col in inspector.get_columns("users")}
        return "email" in columns, "bio" in columns

    has_email, has_bio = await conn.run_sync(get_legacy_user_columns)
    if not has_email:
        return

    dialect = conn.dialect.name
    if dialect == "sqlite":
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        bio_source = "bio" if has_bio else "NULL"
        await conn.execute(text("""
            CREATE TABLE users_without_email (
                username VARCHAR(50) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                full_name VARCHAR(100) NOT NULL,
                role VARCHAR(50) NOT NULL,
                department VARCHAR(100),
                bio TEXT,
                avatar_url VARCHAR(500),
                is_active BOOLEAN NOT NULL,
                id CHAR(32) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (username)
            )
        """))
        await conn.execute(text("""
            INSERT INTO users_without_email (
                username, hashed_password, full_name, role, department, bio,
                avatar_url, is_active, id, created_at, updated_at
            )
            SELECT
                username, hashed_password, full_name, role, department, {bio_source},
                avatar_url, is_active, id, created_at, updated_at
            FROM users
        """.format(bio_source=bio_source)))
        await conn.execute(text("DROP TABLE users"))
        await conn.execute(text("ALTER TABLE users_without_email RENAME TO users"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
    else:
        await conn.execute(text("ALTER TABLE users DROP COLUMN IF EXISTS email"))


async def ensure_user_bio_column(conn) -> None:
    from sqlalchemy import inspect, text

    def needs_bio_column(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        if not inspector.has_table("users"):
            return False
        return all(col["name"] != "bio" for col in inspector.get_columns("users"))

    if not await conn.run_sync(needs_bio_column):
        return

    await conn.execute(text("ALTER TABLE users ADD COLUMN bio TEXT"))


async def ensure_task_schema(conn) -> None:
    from sqlalchemy import inspect, text

    def task_columns(sync_conn) -> set[str]:
        inspector = inspect(sync_conn)
        if not inspector.has_table("tasks"):
            return set()
        return {col["name"] for col in inspector.get_columns("tasks")}

    columns = await conn.run_sync(task_columns)
    if not columns:
        return

    dialect = conn.dialect.name
    if dialect == "postgresql":
        enum_labels = (await conn.execute(text("""
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = 'taskstatus'
            ORDER BY enumsortorder
        """))).scalars().all()
        desired_labels = ["NOT_STARTED", "IN_PROGRESS", "DONE"]
        if enum_labels and enum_labels != desired_labels:
            await conn.execute(text("DROP TYPE IF EXISTS taskstatus_new"))
            await conn.execute(text("CREATE TYPE taskstatus_new AS ENUM ('NOT_STARTED', 'IN_PROGRESS', 'DONE')"))
            await conn.execute(text("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT"))
            await conn.execute(text("""
                ALTER TABLE tasks
                ALTER COLUMN status TYPE taskstatus_new
                USING (
                    CASE status::text
                        WHEN 'BACKLOG' THEN 'NOT_STARTED'
                        WHEN 'TODO' THEN 'NOT_STARTED'
                        WHEN 'IN_REVIEW' THEN 'IN_PROGRESS'
                        WHEN 'backlog' THEN 'NOT_STARTED'
                        WHEN 'todo' THEN 'NOT_STARTED'
                        WHEN 'in_review' THEN 'IN_PROGRESS'
                        WHEN 'not_started' THEN 'NOT_STARTED'
                        WHEN 'in_progress' THEN 'IN_PROGRESS'
                        WHEN 'done' THEN 'DONE'
                        ELSE status::text
                    END
                )::taskstatus_new
            """))
            await conn.execute(text("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'NOT_STARTED'"))
            await conn.execute(text("DROP TYPE taskstatus"))
            await conn.execute(text("ALTER TYPE taskstatus_new RENAME TO taskstatus"))
        if "signed_off_by_id" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN signed_off_by_id UUID"))
        if "signed_off_at" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN signed_off_at TIMESTAMP WITH TIME ZONE"))
    else:
        await conn.execute(text("""
            UPDATE tasks
            SET status = 'NOT_STARTED'
            WHERE status IN ('BACKLOG', 'TODO', 'backlog', 'todo', 'not_started')
        """))
        await conn.execute(text("""
            UPDATE tasks
            SET status = 'IN_PROGRESS'
            WHERE status IN ('IN_REVIEW', 'in_review', 'in_progress')
        """))
        await conn.execute(text("""
            UPDATE tasks
            SET status = 'DONE'
            WHERE status = 'done'
        """))
        if "signed_off_by_id" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN signed_off_by_id CHAR(32)"))
        if "signed_off_at" not in columns:
            await conn.execute(text("ALTER TABLE tasks ADD COLUMN signed_off_at DATETIME"))


async def sync_legacy_permissions(session) -> bool:
    from sqlalchemy import select

    from app.models.permission import RolePermission

    result = await session.execute(select(RolePermission))
    changed = False
    for role_permission in result.scalars().all():
        permissions = list(role_permission.permissions or [])
        if "task.status" not in permissions:
            continue
        next_permissions = []
        for permission in permissions:
            if permission == "task.status":
                if "task.signoff" not in next_permissions:
                    next_permissions.append("task.signoff")
                continue
            if permission not in next_permissions:
                next_permissions.append(permission)
        role_permission.permissions = next_permissions
        changed = True
    if changed:
        await session.flush()
    return changed


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import func, select

    from app.database import async_session, engine
    from app.models import Base
    from app.models.user import User, UserRole
    from app.utils.security import hash_password

    # Auto-create tables on startup. This keeps first-run deployment simple.
    async with engine.begin() as conn:
        await drop_legacy_user_email_column(conn)
        await conn.run_sync(Base.metadata.create_all)
        await ensure_user_bio_column(conn)
        await ensure_task_schema(conn)

    async with async_session() as session:
        if await sync_legacy_permissions(session):
            await session.commit()
        count = (await session.execute(select(func.count(User.id)))).scalar()
        if count == 0:
            users = [
                User(
                    username=settings.ADMIN_USERNAME,
                    hashed_password=hash_password(settings.ADMIN_PASSWORD),
                    full_name=settings.ADMIN_FULL_NAME,
                    role=UserRole.ADMIN,
                )
            ]
            if settings.SEED_DEMO_USERS:
                users.extend([
                    User(
                        username="zhangsan",
                        hashed_password=hash_password("123456"),
                        full_name="Zhang San",
                        role=UserRole.MANAGER,
                    ),
                    User(
                        username="lisi",
                        hashed_password=hash_password("123456"),
                        full_name="Li Si",
                        role=UserRole.MEMBER,
                    ),
                    User(
                        username="wangwu",
                        hashed_password=hash_password("123456"),
                        full_name="Wang Wu",
                        role=UserRole.MEMBER,
                    ),
                ])
            session.add_all(users)
            await session.commit()
            print(f"[OK] Bootstrap admin created: {settings.ADMIN_USERNAME}")
            if settings.SEED_DEMO_USERS:
                print("[OK] Demo users created: zhangsan/123456, lisi/123456, wangwu/123456")

    yield


app = FastAPI(
    title="Project Task Progress Management System",
    description="Project Task Progress Management System API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)


@app.get("/health")
async def health():
    return {"status": "ok"}
