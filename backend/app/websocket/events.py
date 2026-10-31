import logging

from app.websocket.manager import manager

logger = logging.getLogger(__name__)


def queue_project_event(db, project_id=None):
    db.info.setdefault("changed_projects", set()).add(str(project_id) if project_id else None)


async def publish_committed_events(db):
    for project_id in db.info.pop("changed_projects", set()):
        try:
            await manager.broadcast({"type": "project.changed", "data": {"project_id": project_id}})
        except Exception:
            logger.exception("Post-commit project notification failed")


async def emit_task_event(event_type: str, task_data: dict):
    await manager.broadcast({
        "type": event_type,
        "data": task_data,
    })


async def emit_progress_event(progress_data: dict):
    await manager.broadcast({
        "type": "progress.logged",
        "data": progress_data,
    })
