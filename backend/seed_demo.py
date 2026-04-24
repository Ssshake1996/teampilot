"""
Seed demo data for local development.

Run:
    cd backend
    python seed_demo.py
"""

import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from app.database import async_session, engine
from app.models import Base
from app.models.assignment import Assignment, AssignmentKind
from app.models.project import Project, ProjectRole, ProjectStatus
from app.models.skill import Skill, UserSkill
from app.models.system_setting import SystemSetting
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.task_event import TaskEvent, TaskEventType
from app.models.user import User, UserRole
from app.utils.security import hash_password


NOW = datetime.now(timezone.utc)
DEFAULT_PASSWORD = "123456"

LEGACY_TABLES = [
    "task_required_skills",
    "task_progress",
    "task_assignees",
    "project_members",
    "capability_profiles",
    "ai_config",
    "role_permissions",
]


TEAM = [
    {"username": "zhaolei", "full_name": "赵磊", "role": UserRole.MANAGER, "department": "PM"},
    {"username": "sunwei", "full_name": "孙伟", "role": UserRole.MANAGER, "department": "PM"},
    {"username": "qianhua", "full_name": "钱华", "role": UserRole.MANAGER, "department": "PM"},
    {"username": "liuyang", "full_name": "刘洋", "role": UserRole.MEMBER, "department": "TSE"},
    {"username": "chenfei", "full_name": "陈飞", "role": UserRole.MEMBER, "department": "TSE"},
    {"username": "rengang", "full_name": "任刚", "role": UserRole.MEMBER, "department": "性能测试"},
    {"username": "weilan", "full_name": "魏岚", "role": UserRole.MEMBER, "department": "性能测试"},
    {"username": "jiaxin", "full_name": "贾鑫", "role": UserRole.MEMBER, "department": "兼容性测试"},
    {"username": "jiangnan", "full_name": "江南", "role": UserRole.MEMBER, "department": "可靠性测试"},
    {"username": "xiejian", "full_name": "谢健", "role": UserRole.MEMBER, "department": "自动化"},
    {"username": "dengchao", "full_name": "邓超", "role": UserRole.MEMBER, "department": "自动化"},
    {"username": "baili", "full_name": "白丽", "role": UserRole.MEMBER, "department": "测试环境"},
    {"username": "longbin", "full_name": "龙斌", "role": UserRole.MEMBER, "department": "测试环境"},
    {"username": "gaofang", "full_name": "高芳", "role": UserRole.MEMBER, "department": "测试执行"},
]


SKILLS = [
    ("项目管理", "管理"),
    ("需求分析", "管理"),
    ("NVMe 测试", "存储"),
    ("性能测试", "测试"),
    ("兼容性测试", "测试"),
    ("可靠性测试", "测试"),
    ("Python", "开发"),
    ("Pytest", "开发"),
    ("Jenkins", "开发"),
    ("Linux", "平台"),
]


PROJECTS = [
    {
        "name": "NVMe SSD X2 量产前验证",
        "description": "围绕功能、性能、兼容性和可靠性完成量产前收口。",
        "status": ProjectStatus.ACTIVE,
        "owner": "赵磊",
        "start_date": date(2026, 4, 1),
        "end_date": date(2026, 5, 10),
        "members": ["赵磊", "刘洋", "陈飞", "任刚", "魏岚", "贾鑫", "江南", "白丽"],
        "tasks": [
            {
                "title": "固件功能测试",
                "status": TaskStatus.IN_PROGRESS,
                "priority": TaskPriority.HIGH,
                "assignees": ["刘洋", "陈飞"],
                "estimated_hours": 40,
                "start_offset": -5,
                "deadline_offset": 10,
                "progress_pct": 60,
                "note": "基础命令验证完成，正在补异常场景。",
                "children": [
                    {"title": "NVMe Admin Command 测试", "status": TaskStatus.DONE, "priority": TaskPriority.HIGH, "assignees": ["刘洋"], "estimated_hours": 8, "start_offset": -8, "deadline_offset": -2, "progress_pct": 100},
                    {"title": "Error Injection 测试", "status": TaskStatus.NOT_STARTED, "priority": TaskPriority.MEDIUM, "assignees": ["陈飞"], "estimated_hours": 6, "start_offset": 2, "deadline_offset": 6},
                ],
            },
            {
                "title": "4K 随机性能基线",
                "status": TaskStatus.IN_PROGRESS,
                "priority": TaskPriority.HIGH,
                "assignees": ["任刚", "魏岚"],
                "estimated_hours": 24,
                "start_offset": -3,
                "deadline_offset": 8,
                "progress_pct": 45,
                "note": "读性能完成，写性能和混合负载待补。",
            },
            {
                "title": "平台兼容性验证",
                "status": TaskStatus.NOT_STARTED,
                "priority": TaskPriority.MEDIUM,
                "assignees": ["贾鑫"],
                "estimated_hours": 24,
                "start_offset": 3,
                "deadline_offset": 15,
            },
            {
                "title": "掉电一致性测试",
                "status": TaskStatus.NOT_STARTED,
                "priority": TaskPriority.URGENT,
                "assignees": ["江南", "白丽"],
                "estimated_hours": 32,
                "start_offset": 4,
                "deadline_offset": 18,
            },
        ],
    },
    {
        "name": "自动化回归平台升级",
        "description": "统一到 Pytest + Allure + Jenkins 的执行链路。",
        "status": ProjectStatus.ACTIVE,
        "owner": "孙伟",
        "start_date": date(2026, 4, 5),
        "end_date": date(2026, 6, 30),
        "members": ["孙伟", "谢健", "邓超", "龙斌", "白丽"],
        "tasks": [
            {
                "title": "Pytest 基础框架搭建",
                "status": TaskStatus.DONE,
                "priority": TaskPriority.HIGH,
                "assignees": ["谢健"],
                "estimated_hours": 20,
                "start_offset": -20,
                "deadline_offset": -10,
                "progress_pct": 100,
            },
            {
                "title": "Allure 报告集成",
                "status": TaskStatus.IN_PROGRESS,
                "priority": TaskPriority.HIGH,
                "assignees": ["邓超", "龙斌"],
                "estimated_hours": 16,
                "start_offset": -2,
                "deadline_offset": 7,
                "progress_pct": 55,
                "note": "报告产出链路通了，邮件分发和权限还在补。",
            },
            {
                "title": "SSD 回归用例迁移",
                "status": TaskStatus.NOT_STARTED,
                "priority": TaskPriority.MEDIUM,
                "assignees": ["谢健", "邓超"],
                "estimated_hours": 36,
                "start_offset": 5,
                "deadline_offset": 25,
            },
        ],
    },
    {
        "name": "银行 POC 环境验证",
        "description": "完成部署、迁移方案验证和压力测试。",
        "status": ProjectStatus.ACTIVE,
        "owner": "钱华",
        "start_date": date(2026, 4, 10),
        "end_date": date(2026, 4, 28),
        "members": ["钱华", "高芳", "刘洋", "白丽"],
        "tasks": [
            {
                "title": "POC 方案评审",
                "status": TaskStatus.DONE,
                "priority": TaskPriority.HIGH,
                "assignees": ["钱华"],
                "estimated_hours": 8,
                "start_offset": -7,
                "deadline_offset": -5,
                "progress_pct": 100,
            },
            {
                "title": "环境部署与初始化",
                "status": TaskStatus.IN_PROGRESS,
                "priority": TaskPriority.HIGH,
                "assignees": ["刘洋", "白丽"],
                "estimated_hours": 18,
                "start_offset": -1,
                "deadline_offset": 4,
                "progress_pct": 50,
                "note": "设备已上架，网络策略待客户确认。",
            },
            {
                "title": "OLTP 压力测试",
                "status": TaskStatus.NOT_STARTED,
                "priority": TaskPriority.MEDIUM,
                "assignees": ["高芳"],
                "estimated_hours": 12,
                "start_offset": 2,
                "deadline_offset": 9,
            },
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
    assignees: list[str],
    estimated_hours: int | float,
    start_offset: int,
    deadline_offset: int,
    progress_pct: int | None = None,
    note: str | None = None,
    parent_task: Task | None = None,
    sort_order: int = 0,
) -> Task:
    start_date = dt_with_offset(start_offset)
    deadline = dt_with_offset(deadline_offset)
    completed_at = dt_with_offset(deadline_offset - 1) if status == TaskStatus.DONE else None
    assignee_users = [users_by_name[name] for name in assignees if name in users_by_name]

    task = Task(
        project_id=project.id,
        title=title,
        status=status,
        priority=priority,
        creator_id=creator.id,
        parent_task_id=parent_task.id if parent_task else None,
        estimated_hours=Decimal(str(estimated_hours)),
        start_date=start_date,
        deadline=deadline,
        completed_at=completed_at,
        signed_off_by_id=creator.id if status == TaskStatus.DONE else None,
        signed_off_at=completed_at if status == TaskStatus.DONE else None,
        sort_order=sort_order,
    )
    db.add(task)
    await db.flush()

    for user in assignee_users:
        db.add(Assignment(
            project_id=project.id,
            task_id=task.id,
            user_id=user.id,
            kind=AssignmentKind.TASK_ASSIGNEE,
            role="assignee",
        ))

    if progress_pct is not None and assignee_users:
        db.add(
            TaskEvent(
                task_id=task.id,
                actor_id=assignee_users[0].id,
                event_type=TaskEventType.PROGRESS,
                progress_pct=progress_pct,
                note=note or "进展已同步",
                hours_spent=Decimal(str(max(1, round(float(estimated_hours) * progress_pct / 100, 1)))),
            )
        )

    return task


async def seed() -> None:
    async with engine.begin() as conn:
        cascade = " CASCADE" if conn.dialect.name == "postgresql" else ""
        for table_name in LEGACY_TABLES:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table_name}{cascade}"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        admin = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            full_name="系统管理员",
            role=UserRole.ADMIN,
            department="管理",
        )
        db.add(admin)

        users: list[User] = []
        for member in TEAM:
            user = User(
                username=member["username"],
                hashed_password=hash_password(DEFAULT_PASSWORD),
                full_name=member["full_name"],
                role=member["role"],
                department=member["department"],
                bio=f"{member['full_name']}，来自{member['department']}，用于本地演示数据。",
            )
            db.add(user)
            users.append(user)
        await db.flush()

        users_by_name = {user.full_name: user for user in users}

        skills: dict[str, Skill] = {}
        for name, category in SKILLS:
            skill = Skill(name=name, category=category)
            db.add(skill)
            skills[name] = skill
        await db.flush()

        skill_map = {
            "PM": ["项目管理", "需求分析"],
            "TSE": ["NVMe 测试", "Linux"],
            "性能测试": ["性能测试", "Linux"],
            "兼容性测试": ["兼容性测试", "Linux"],
            "可靠性测试": ["可靠性测试", "Linux"],
            "自动化": ["Python", "Pytest", "Jenkins"],
            "测试环境": ["Linux", "Jenkins"],
            "测试执行": ["性能测试", "Linux"],
        }
        for user in users:
            for skill_name in skill_map.get(user.department or "", []):
                db.add(
                    UserSkill(
                        user_id=user.id,
                        skill_id=skills[skill_name].id,
                        proficiency=random.randint(3, 5),
                    )
                )

        sort_order = 0
        for item in PROJECTS:
            owner = users_by_name[item["owner"]]
            project = Project(
                name=item["name"],
                goal=item.get("goal") or item["description"],
                description=item["description"],
                status=item["status"],
                owner_id=owner.id,
                start_date=item["start_date"],
                end_date=item["end_date"],
            )
            db.add(project)
            await db.flush()

            for member_name in item["members"]:
                db.add(
                    Assignment(
                        project_id=project.id,
                        user_id=users_by_name[member_name].id,
                        kind=AssignmentKind.PROJECT_MEMBER,
                        role=(ProjectRole.LEAD.value if member_name == item["owner"] else ProjectRole.MEMBER.value),
                    )
                )

            for task_item in item["tasks"]:
                sort_order += 1
                parent = await add_task(
                    db=db,
                    project=project,
                    creator=owner,
                    users_by_name=users_by_name,
                    title=task_item["title"],
                    status=task_item["status"],
                    priority=task_item["priority"],
                    assignees=task_item["assignees"],
                    estimated_hours=task_item["estimated_hours"],
                    start_offset=task_item["start_offset"],
                    deadline_offset=task_item["deadline_offset"],
                    progress_pct=task_item.get("progress_pct"),
                    note=task_item.get("note"),
                    sort_order=sort_order,
                )
                for child in task_item.get("children", []):
                    sort_order += 1
                    await add_task(
                        db=db,
                        project=project,
                        creator=owner,
                        users_by_name=users_by_name,
                        title=child["title"],
                        status=child["status"],
                        priority=child["priority"],
                        assignees=child["assignees"],
                        estimated_hours=child["estimated_hours"],
                        start_offset=child["start_offset"],
                        deadline_offset=child["deadline_offset"],
                        progress_pct=child.get("progress_pct"),
                        note=child.get("note"),
                        parent_task=parent,
                        sort_order=sort_order,
                    )

        db.add(
            SystemSetting(
                key="ai_config",
                value_json={
                    "api_base_url": "https://coding.dashscope.aliyuncs.com/v1",
                    "api_key_encrypted": "",
                    "model_name": "qwen3.5-plus",
                    "max_tokens": 4096,
                    "temperature": 0.7,
                },
            )
        )

        await db.commit()
        print(f"[OK] Seeded admin/admin123 and {len(users)} demo users")
        print(f"[OK] Default member password: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
