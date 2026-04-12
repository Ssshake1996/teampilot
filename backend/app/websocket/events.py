from app.websocket.manager import manager


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
