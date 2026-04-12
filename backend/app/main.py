from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.utils.security import decode_token
from app.websocket.manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on startup (dev mode)
    from app.database import engine
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default admin user if empty
    from app.database import async_session
    from sqlalchemy import select, func
    async with async_session() as session:
        from app.models.user import User, UserRole
        count = (await session.execute(select(func.count(User.id)))).scalar()
        if count == 0:
            from app.utils.security import hash_password
            admin = User(
                username="admin",
                email="admin@teampilot.com",
                hashed_password=hash_password("admin123"),
                full_name="系统管理员",
                role=UserRole.ADMIN,
            )
            demo1 = User(
                username="zhangsan",
                email="zhangsan@teampilot.com",
                hashed_password=hash_password("123456"),
                full_name="张三",
                role=UserRole.MANAGER,
            )
            demo2 = User(
                username="lisi",
                email="lisi@teampilot.com",
                hashed_password=hash_password("123456"),
                full_name="李四",
                role=UserRole.MEMBER,
            )
            demo3 = User(
                username="wangwu",
                email="wangwu@teampilot.com",
                hashed_password=hash_password("123456"),
                full_name="王五",
                role=UserRole.MEMBER,
            )
            session.add_all([admin, demo1, demo2, demo3])
            await session.commit()
            print("[OK] Default users created: admin/admin123, zhangsan/123456, lisi/123456, wangwu/123456")

    yield


app = FastAPI(
    title="项目任务进度管理系统",
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
