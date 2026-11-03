"""Role-based permission configuration."""

ROLE_PERMISSIONS_KEY = "role_permissions"
BUILTIN_ROLES = {"admin", "manager", "member"}

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
            ("task.edit", "编辑任务"),
            ("task.assign", "分配负责人"),
            ("task.signoff", "任务完成会签"),
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
            ("personnel.edit", "编辑人员资料"),
            ("personnel.deactivate", "删除/停用人员"),
            ("personnel.edit_skills", "编辑技能"),
            ("personnel.view_detail", "查看人员详情"),
        ],
    },
    "system": {
        "label": "系统设置",
        "items": [
            ("system.role_manage", "角色权限管理"),
            ("system.skill_manage", "技能标签管理"),
            ("system.model_manage", "模型配置管理"),
        ],
    },
}


def normalize_permissions(permissions: list[str]) -> list[str]:
    """Keep existing delegated settings access after the feature rename."""
    return list(dict.fromkeys(
        "system.model_manage" if permission == "system.connector_manage" else permission
        for permission in permissions
    ))

DEFAULT_PERMISSIONS = {
    "admin": [permission for category in PERMISSION_CATALOG.values() for permission, _ in category["items"]],
    "manager": [
        "project.create", "project.edit", "project.member.manage",
        "task.create", "task.edit", "task.assign", "task.signoff", "task.delete",
        "task.set_deadline", "task.set_hours",
        "progress.submit", "progress.view",
        "personnel.edit", "personnel.edit_skills", "personnel.view_detail",
    ],
    "member": [
        "progress.submit", "progress.view",
        "personnel.view_detail",
    ],
}
