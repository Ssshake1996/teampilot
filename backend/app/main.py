import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.utils.security import decode_token
from app.websocket.manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import func, select

    from app.database import async_session
    from app.models.user import User, UserRole
    from app.migrations import upgrade_database
    from app.utils.security import hash_password

    if settings.AUTO_MIGRATE:
        await asyncio.to_thread(upgrade_database)

    async with async_session() as session:
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
                print("[OK] Development demo accounts created")
        await session.commit()

    from app.services.report_service import report_scheduler_loop

    report_scheduler = asyncio.create_task(report_scheduler_loop())
    try:
        yield
    finally:
        report_scheduler.cancel()
        try:
            await report_scheduler
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Project Task Progress Management System",
    description="Project Task Progress Management System API",
    version="0.4.0",
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    from sqlalchemy import select
    from app.database import async_session
    from app.models.user import User

    origin = websocket.headers.get("origin")
    allowed = set(settings.CORS_ORIGINS)
    for item in settings.CORS_ORIGINS:
        if "://localhost:" in item:
            allowed.add(item.replace("://localhost:", "://127.0.0.1:"))
        if "://127.0.0.1:" in item:
            allowed.add(item.replace("://127.0.0.1:", "://localhost:"))
    if origin and origin not in allowed:
        await websocket.close(code=4003)
        return
    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        token = auth.get("token") if isinstance(auth, dict) else None
        if not isinstance(token, str):
            raise ValueError("Invalid token format")
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            raise ValueError("Invalid access token")
        user_id = str(uuid.UUID(payload["sub"]))
        async with async_session() as session:
            active = (await session.execute(select(User.is_active).where(User.id == uuid.UUID(user_id)))).scalar()
        if not active:
            raise ValueError("Inactive account")
    except (ValueError, KeyError, asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close(code=4001)
        return
    await manager.connect(websocket, user_id, accepted=True)
    await websocket.send_json({"type": "connection.ready", "data": {}})
    try:
        async with asyncio.timeout(max(1, payload["exp"] - time.time())):
            while True:
                await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except TimeoutError:
        await websocket.close(code=4001)
    finally:
        manager.disconnect(websocket, user_id)


@app.get("/health")
async def health():
    return {"status": "ok"}
