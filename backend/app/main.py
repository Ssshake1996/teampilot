import asyncio
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

    from app.database import async_session, engine
    from app.models import Base
    from app.models.user import User, UserRole
    from app.utils.security import hash_password

    # Auto-create tables on startup. Schema drift is handled explicitly in code
    # and tests instead of startup-time compatibility patches.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
                print("[OK] Demo users created: zhangsan/123456, lisi/123456, wangwu/123456")

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
