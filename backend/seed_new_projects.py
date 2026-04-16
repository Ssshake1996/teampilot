"""
Append a few current-format demo projects into an existing database.

Run:
    cd backend
    python seed_new_projects.py
"""

import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.database import async_session
from app.models.project import Project, ProjectMember, ProjectRole, ProjectStatus
from app.models.task import Task, TaskAssignee, TaskPriority, TaskStatus
from app.models.task_progress import TaskProgress
from app.models.user import User


NOW = datetime.now(timezone.utc)


PROJECTS = [
    {
        "name": "对象存储回归专项",
        "description": "补齐对象存储接口稳定性、限流和告警链路回归。",
        "owner": "赵磊",
        "status": ProjectStatus.ACTIVE,
        "start_date": date(2026, 4, 15),
        "end_date": date(2026, 5, 30),
        "members": ["赵磊", "刘洋", "陈飞", "谢健", "邓超"],
        "tasks": [
            ("S3 兼容性回归", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, ["刘洋", "陈飞"], 20, -2, 6, 50),
            ("异常码覆盖补齐", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM, ["陈飞"], 10, 2, 10, None),
            ("接口自动化接入", TaskStatus.NOT_STARTED, TaskPriority.HIGH, ["谢健", "邓超"], 24, 3, 14, None),
        ],
    },
    {
        "name": "测试数据治理",
        "description": "统一测试数据模板、字段字典和结果回收策略。",
        "owner": "孙伟",
        "status": ProjectStatus.ACTIVE,
        "start_date": date(2026, 4, 18),
        "end_date": date(2026, 6, 15),
        "members": ["孙伟", "白丽", "龙斌", "高芳"],
        "tasks": [
            ("历史数据盘点", TaskStatus.DONE, TaskPriority.MEDIUM, ["白丽"], 8, -6, -3, 100),
            ("统一模板设计", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, ["龙斌", "高芳"], 18, -1, 8, 40),
            ("回收归档脚本", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM, ["龙斌"], 12, 5, 15, None),
        ],
    },
    {
        "name": "日报巡检优化",
        "description": "增强日报汇总、风险提取和自动提醒链路。",
        "owner": "钱华",
        "status": ProjectStatus.ACTIVE,
        "start_date": date(2026, 4, 20),
        "end_date": date(2026, 5, 20),
        "members": ["钱华", "任刚", "魏岚", "谢健"],
        "tasks": [
            ("风险规则补强", TaskStatus.IN_PROGRESS, TaskPriority.HIGH, ["钱华", "任刚"], 16, -1, 5, 65),
            ("AI 提示词收敛", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM, ["谢健"], 10, 2, 9, None),
            ("巡检结果通知联调", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM, ["魏岚", "钱华"], 12, 4, 12, None),
        ],
    },
]


def dt_with_offset(days: int) -> datetime:
    return NOW + timedelta(days=days)


async def add_task(
    db,
    project: Project,
    creator: User,
    users_by_name: dict[str, User],
    title: str,
    status: TaskStatus,
    priority: TaskPriority,
    assignee_names: list[str],
    estimated_hours: int | float,
    start_offset: int,
    deadline_offset: int,
    progress_pct: int | None,
    sort_order: int,
) -> None:
    completed_at = dt_with_offset(deadline_offset - 1) if status == TaskStatus.DONE else None
    task = Task(
        project_id=project.id,
        title=title,
        status=status,
        priority=priority,
        creator_id=creator.id,
        estimated_hours=Decimal(str(estimated_hours)),
        start_date=dt_with_offset(start_offset),
        deadline=dt_with_offset(deadline_offset),
        completed_at=completed_at,
        signed_off_by_id=creator.id if status == TaskStatus.DONE else None,
        signed_off_at=completed_at if status == TaskStatus.DONE else None,
        sort_order=sort_order,
    )
    db.add(task)
    await db.flush()

    assignees = [users_by_name[name] for name in assignee_names if name in users_by_name]
    for user in assignees:
        db.add(TaskAssignee(task_id=task.id, user_id=user.id))

    if progress_pct is not None and assignees:
        db.add(
            TaskProgress(
                task_id=task.id,
                user_id=assignees[0].id,
                progress_pct=progress_pct,
                note="种子数据初始化进展",
                hours_spent=Decimal(str(max(1, round(float(estimated_hours) * progress_pct / 100, 1)))),
            )
        )


async def seed() -> None:
    async with async_session() as db:
        users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
        if not users:
            raise RuntimeError("No users found. Run seed_demo.py first.")

        users_by_name = {user.full_name: user for user in users}

        sort_order = 0
        for item in PROJECTS:
            owner = users_by_name.get(item["owner"], random.choice(users))
            project = Project(
                name=item["name"],
                description=item["description"],
                status=item["status"],
                owner_id=owner.id,
                start_date=item["start_date"],
                end_date=item["end_date"],
            )
            db.add(project)
            await db.flush()

            for member_name in item["members"]:
                user = users_by_name.get(member_name)
                if not user:
                    continue
                db.add(
                    ProjectMember(
                        project_id=project.id,
                        user_id=user.id,
                        role_in_project=ProjectRole.LEAD if user.id == owner.id else ProjectRole.MEMBER,
                    )
                )

            for task_item in item["tasks"]:
                sort_order += 1
                await add_task(
                    db=db,
                    project=project,
                    creator=owner,
                    users_by_name=users_by_name,
                    title=task_item[0],
                    status=task_item[1],
                    priority=task_item[2],
                    assignee_names=task_item[3],
                    estimated_hours=task_item[4],
                    start_offset=task_item[5],
                    deadline_offset=task_item[6],
                    progress_pct=task_item[7],
                    sort_order=sort_order,
                )

        await db.commit()
        print(f"[OK] Added {len(PROJECTS)} projects with current task schema")


if __name__ == "__main__":
    asyncio.run(seed())
