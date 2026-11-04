from fastapi import APIRouter, Depends

from app.api import auth, users, projects, tasks, skills, capabilities, dashboard, permissions, data_skills, reports, model_providers
from app.api import project_access, task_management, team_planning
from app.services.project_access_service import scoped_request_access

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router, dependencies=[Depends(scoped_request_access)])
api_router.include_router(tasks.router, dependencies=[Depends(scoped_request_access)])
api_router.include_router(skills.router)
api_router.include_router(capabilities.router)
api_router.include_router(dashboard.router)
api_router.include_router(permissions.router)
api_router.include_router(data_skills.router, dependencies=[Depends(scoped_request_access)])
api_router.include_router(reports.router)
api_router.include_router(model_providers.router)
api_router.include_router(project_access.router)
api_router.include_router(task_management.router)
api_router.include_router(team_planning.router)
