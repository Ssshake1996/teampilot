"""Role-based permission configuration."""
from sqlalchemy import String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


# All available permissions grouped by category
PERMISSION_CATALOG = {
    "project": {
        "label": "项目管理",
        "items": [
            ("project.create", "创建项目"),
            ("project.edit", "编辑项目"),
            ("project.archive", "归档项目"),
            ("project.member.manage", "管理项目成员"),
        ],
    },
    "task": {
        "label": "任务管理",
        "items": [
            ("task.create", "创建任务/子任务"),
            ("task.edit", "编辑任务(标题/描述/优先级)"),
            ("task.assign", "分配负责人"),
            ("task.status", "修改任务状态"),
            ("task.delete", "删除任务"),
            ("task.set_deadline", "设置截止日期"),
            ("task.set_hours", "设置工时"),
        ],
    },
    "progress": {
        "label": "进度反馈",
        "items": [
            ("progress.submit", "提交进度反馈"),
            ("progress.view", "查看进度历史"),
        ],
    },
    "personnel": {
        "label": "人员管理",
        "items": [
            ("personnel.add", "添加人员"),
            ("personnel.deactivate", "停用人员"),
            ("personnel.edit_skills", "编辑技能"),
            ("personnel.view_detail", "查看人员详情"),
        ],
    },
    "ai": {
        "label": "AI 功能",
        "items": [
            ("ai.estimate", "AI 推荐/预估"),
            ("ai.risk", "AI 风险分析"),
            ("ai.capability", "AI 能力分析"),
            ("ai.config", "AI 配置管理"),
            ("ai.prompt", "AI Prompt 配置"),
        ],
    },
    "system": {
        "label": "系统设置",
        "items": [
            ("system.role_manage", "角色权限管理"),
            ("system.skill_manage", "技能标签管理"),
        ],
    },
}

# Default permissions per role
DEFAULT_PERMISSIONS = {
    "admin": [p for cat in PERMISSION_CATALOG.values() for p, _ in cat["items"]],
    "manager": [
        "project.create", "project.edit", "project.member.manage",
        "task.create", "task.edit", "task.assign", "task.status", "task.delete",
        "task.set_deadline", "task.set_hours",
        "progress.submit", "progress.view",
        "personnel.edit_skills", "personnel.view_detail",
        "ai.estimate", "ai.risk", "ai.capability",
    ],
    "member": [
        "progress.submit", "progress.view",
        "personnel.view_detail",
        "ai.estimate",
    ],
}


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role: Mapped[str] = mapped_column(String(50), primary_key=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
