from fastapi import APIRouter

from app.api import auth, users, projects, tasks, skills, capabilities, dashboard, ai, permissions, data_skills

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(skills.router)
api_router.include_router(capabilities.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai.router)
api_router.include_router(permissions.router)
api_router.include_router(data_skills.router)
