"""
Seed script: Create demo data for a storage testing company.
Run: cd backend && python seed_demo.py
"""
import asyncio
import uuid
import random
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine, async_session
from app.models import Base
from app.models.user import User, UserRole
from app.models.project import Project, ProjectMember, ProjectStatus, ProjectRole
from app.models.task import Task, TaskStatus, TaskPriority, TaskRequiredSkill
from app.models.skill import Skill, UserSkill
from app.models.task_progress import TaskProgress
from app.models.capability_profile import AIConfig
from app.utils.security import hash_password

NOW = datetime.now(timezone.utc)
PASSWORD = hash_password("123456")


# ── Team Members ──────────────────────────────────────────────
TEAM = [
    # Project Management (PM)
    {"username": "zhaolei",    "full_name": "赵磊",   "role": UserRole.MANAGER, "group": "PM"},
    {"username": "sunwei",     "full_name": "孙伟",   "role": UserRole.MANAGER, "group": "PM"},
    {"username": "qianhua",    "full_name": "钱华",   "role": UserRole.MANAGER, "group": "PM"},
    # TSE (Technical Support Engineer)
    {"username": "liuyang",    "full_name": "刘洋",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "chenfei",    "full_name": "陈飞",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "yangming",   "full_name": "杨明",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "huangjie",   "full_name": "黄杰",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "zhoujun",    "full_name": "周军",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "wuqiang",    "full_name": "吴强",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "xuting",     "full_name": "徐婷",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "malin",      "full_name": "马琳",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "zhubin",     "full_name": "朱斌",   "role": UserRole.MEMBER, "group": "TSE"},
    {"username": "hexiang",    "full_name": "何翔",   "role": UserRole.MEMBER, "group": "TSE"},
    # Test Execution
    {"username": "gaofang",    "full_name": "高芳",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "linbo",      "full_name": "林波",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "guoyu",      "full_name": "郭宇",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "luodan",     "full_name": "罗丹",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "liangxin",   "full_name": "梁鑫",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "songjia",    "full_name": "宋佳",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "tanghao",    "full_name": "唐浩",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "fengna",     "full_name": "冯娜",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "hanpeng",    "full_name": "韩鹏",   "role": UserRole.MEMBER, "group": "测试执行"},
    {"username": "caolei",     "full_name": "曹磊",   "role": UserRole.MEMBER, "group": "测试执行"},
    # Automation
    {"username": "xiejian",    "full_name": "谢健",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "dengchao",   "full_name": "邓超",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "xiaoli",     "full_name": "萧丽",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "panwei",     "full_name": "潘伟",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "jiangyi",    "full_name": "蒋毅",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "yulong",     "full_name": "余龙",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "duming",     "full_name": "杜明",   "role": UserRole.MEMBER, "group": "自动化"},
    {"username": "yexue",      "full_name": "叶雪",   "role": UserRole.MEMBER, "group": "自动化"},
    # Performance Testing
    {"username": "rengang",    "full_name": "任刚",   "role": UserRole.MEMBER, "group": "性能测试"},
    {"username": "weilan",     "full_name": "魏岚",   "role": UserRole.MEMBER, "group": "性能测试"},
    {"username": "fanyi",      "full_name": "范毅",   "role": UserRole.MEMBER, "group": "性能测试"},
    {"username": "shikai",     "full_name": "石凯",   "role": UserRole.MEMBER, "group": "性能测试"},
    {"username": "taoyu",      "full_name": "陶宇",   "role": UserRole.MEMBER, "group": "性能测试"},
    # Compatibility Testing
    {"username": "jiaxin",     "full_name": "贾鑫",   "role": UserRole.MEMBER, "group": "兼容性测试"},
    {"username": "zouhui",     "full_name": "邹慧",   "role": UserRole.MEMBER, "group": "兼容性测试"},
    {"username": "xiongwei",   "full_name": "熊伟",   "role": UserRole.MEMBER, "group": "兼容性测试"},
    {"username": "qinjie",     "full_name": "秦杰",   "role": UserRole.MEMBER, "group": "兼容性测试"},
    # Reliability Testing
    {"username": "jiangnan",   "full_name": "江南",   "role": UserRole.MEMBER, "group": "可靠性测试"},
    {"username": "luyu",       "full_name": "陆宇",   "role": UserRole.MEMBER, "group": "可靠性测试"},
    {"username": "kongfei",    "full_name": "孔飞",   "role": UserRole.MEMBER, "group": "可靠性测试"},
    # Test Environment & Infra
    {"username": "baili",      "full_name": "白丽",   "role": UserRole.MEMBER, "group": "测试环境"},
    {"username": "houliang",   "full_name": "侯亮",   "role": UserRole.MEMBER, "group": "测试环境"},
    {"username": "longbin",    "full_name": "龙斌",   "role": UserRole.MEMBER, "group": "测试环境"},
]

# ── Skills ────────────────────────────────────────────────────
SKILLS = [
    ("RAID 测试", "存储"),  ("JBOD 测试", "存储"),  ("NVMe 测试", "存储"),
    ("SSD 固件测试", "存储"), ("HDD 兼容性", "存储"),  ("存储协议分析", "存储"),
    ("FIO", "工具"),        ("vdbench", "工具"),      ("IOmeter", "工具"),
    ("CrystalDiskMark", "工具"), ("S.M.A.R.T 分析", "工具"),
    ("Python", "编程"),     ("Shell", "编程"),        ("Robot Framework", "自动化"),
    ("Pytest", "自动化"),   ("Jenkins CI", "自动化"), ("Selenium", "自动化"),
    ("Linux 系统", "平台"), ("Windows Server", "平台"), ("VMware ESXi", "平台"),
    ("项目管理", "软技能"), ("需求分析", "软技能"),    ("测试方案设计", "软技能"),
    ("缺陷分析", "软技能"), ("性能调优", "性能"),      ("基准测试", "性能"),
    ("压力测试", "性能"),   ("数据一致性校验", "可靠性"), ("掉电保护测试", "可靠性"),
    ("长稳测试", "可靠性"),
]

# ── Projects ──────────────────────────────────────────────────
PROJECTS = [
    {
        "name": "企业级 SSD X1 系列认证测试",
        "desc": "针对 X1 系列企业级 NVMe SSD 进行全面认证测试，覆盖性能、兼容性、可靠性、固件功能等维度。",
        "status": ProjectStatus.ACTIVE,
        "start": date(2026, 3, 1),
        "end": date(2026, 6, 30),
    },
    {
        "name": "全闪存阵列 V3.0 版本验证",
        "desc": "V3.0 新增 NVMe-oF、自动分层和快照功能，需对新特性和回归场景进行完整测试。",
        "status": ProjectStatus.ACTIVE,
        "start": date(2026, 2, 15),
        "end": date(2026, 5, 31),
    },
    {
        "name": "分布式存储 CephFS 适配测试",
        "desc": "在公司自研服务器平台上验证 CephFS 集群的部署、扩容、故障恢复和性能基线。",
        "status": ProjectStatus.ACTIVE,
        "start": date(2026, 3, 15),
        "end": date(2026, 7, 15),
    },
    {
        "name": "自动化测试框架 2.0 升级",
        "desc": "将现有 Robot Framework 测试框架升级为 Pytest + Allure 体系，提升用例覆盖率和 CI 集成能力。",
        "status": ProjectStatus.ACTIVE,
        "start": date(2026, 4, 1),
        "end": date(2026, 8, 31),
    },
    {
        "name": "HDD 大容量盘片可靠性长稳测试",
        "desc": "对 20TB/22TB 企业级 HDD 进行 1000 小时长稳测试和掉电数据一致性验证。",
        "status": ProjectStatus.PLANNING,
        "start": date(2026, 5, 1),
        "end": date(2026, 10, 31),
    },
]

# ── Task Templates Per Project ────────────────────────────────
TASKS_BY_PROJECT = {
    0: [  # SSD X1
        ("制定 X1 SSD 测试方案", "PM", TaskPriority.HIGH, TaskStatus.DONE, 16, -30, [
            ("评审固件 Spec 文档", "TSE", TaskPriority.HIGH, TaskStatus.DONE, 8, -28),
            ("编写测试用例矩阵", "TSE", TaskPriority.HIGH, TaskStatus.DONE, 12, -25),
            ("搭建 NVMe 测试环境", "测试环境", TaskPriority.MEDIUM, TaskStatus.DONE, 8, -22),
        ]),
        ("顺序读写性能基线测试", "性能测试", TaskPriority.HIGH, TaskStatus.DONE, 24, -15, []),
        ("随机 4K IOPS 性能测试", "性能测试", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 20, 5, [
            ("4K 随机读测试 (QD1-QD256)", "性能测试", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 8, 3),
            ("4K 随机写测试 (QD1-QD256)", "性能测试", TaskPriority.HIGH, TaskStatus.TODO, 8, 5),
            ("混合读写比例测试 (70/30, 50/50)", "性能测试", TaskPriority.MEDIUM, TaskStatus.TODO, 6, 5),
        ]),
        ("Windows/Linux 兼容性测试", "兼容性测试", TaskPriority.MEDIUM, TaskStatus.IN_PROGRESS, 32, 15, [
            ("Windows Server 2022 识别测试", "兼容性测试", TaskPriority.MEDIUM, TaskStatus.DONE, 6, -5),
            ("Ubuntu 22.04 驱动兼容测试", "兼容性测试", TaskPriority.MEDIUM, TaskStatus.IN_PROGRESS, 6, 10),
            ("VMware ESXi 8.0 直通测试", "兼容性测试", TaskPriority.MEDIUM, TaskStatus.TODO, 8, 15),
            ("UEFI/Legacy 启动测试", "兼容性测试", TaskPriority.LOW, TaskStatus.BACKLOG, 4, 15),
        ]),
        ("掉电数据保护测试", "可靠性测试", TaskPriority.URGENT, TaskStatus.TODO, 40, 20, []),
        ("S.M.A.R.T 属性验证", "TSE", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 12, 25, []),
        ("固件在线升级测试", "TSE", TaskPriority.HIGH, TaskStatus.TODO, 16, 12, []),
        ("温度循环压力测试", "可靠性测试", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 24, 30, []),
    ],
    1: [  # 全闪存阵列 V3.0
        ("NVMe-oF 功能验证", "TSE", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 40, 10, [
            ("TCP Transport 连接测试", "TSE", TaskPriority.HIGH, TaskStatus.DONE, 8, -5),
            ("RDMA Transport 连接测试", "TSE", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 10, 5),
            ("多路径切换测试", "TSE", TaskPriority.HIGH, TaskStatus.TODO, 12, 10),
            ("Namespace 管理测试", "TSE", TaskPriority.MEDIUM, TaskStatus.TODO, 8, 10),
        ]),
        ("自动分层策略测试", "测试执行", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 32, 15, [
            ("热数据上迁测试", "测试执行", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 8, 10),
            ("冷数据下迁测试", "测试执行", TaskPriority.HIGH, TaskStatus.TODO, 8, 15),
            ("分层策略并发测试", "测试执行", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 10, 15),
        ]),
        ("快照功能回归测试", "测试执行", TaskPriority.MEDIUM, TaskStatus.TODO, 24, 20, []),
        ("控制器故障切换测试", "可靠性测试", TaskPriority.URGENT, TaskStatus.IN_PROGRESS, 20, 8, []),
        ("管理界面功能测试", "测试执行", TaskPriority.LOW, TaskStatus.BACKLOG, 16, 25, []),
        ("V3.0 性能对比基线", "性能测试", TaskPriority.HIGH, TaskStatus.TODO, 24, 18, []),
    ],
    2: [  # CephFS
        ("Ceph 集群部署验证", "测试环境", TaskPriority.HIGH, TaskStatus.DONE, 24, -20, []),
        ("CephFS 挂载兼容性测试", "测试执行", TaskPriority.MEDIUM, TaskStatus.IN_PROGRESS, 16, 10, []),
        ("OSD 扩容在线测试", "TSE", TaskPriority.HIGH, TaskStatus.TODO, 16, 15, []),
        ("单 OSD 故障恢复测试", "可靠性测试", TaskPriority.URGENT, TaskStatus.IN_PROGRESS, 20, 5, []),
        ("多客户端并发 IO 测试", "性能测试", TaskPriority.HIGH, TaskStatus.TODO, 24, 20, []),
        ("数据校验与一致性测试", "可靠性测试", TaskPriority.HIGH, TaskStatus.BACKLOG, 20, 25, []),
    ],
    3: [  # 自动化框架 2.0
        ("Pytest 框架基础搭建", "自动化", TaskPriority.HIGH, TaskStatus.DONE, 20, -15, []),
        ("Allure 报告集成", "自动化", TaskPriority.HIGH, TaskStatus.IN_PROGRESS, 12, 5, []),
        ("旧 RF 用例迁移 - SSD 模块", "自动化", TaskPriority.MEDIUM, TaskStatus.IN_PROGRESS, 40, 30, [
            ("迁移性能测试用例", "自动化", TaskPriority.MEDIUM, TaskStatus.IN_PROGRESS, 12, 20),
            ("迁移兼容性测试用例", "自动化", TaskPriority.MEDIUM, TaskStatus.TODO, 12, 25),
            ("迁移可靠性测试用例", "自动化", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 16, 30),
        ]),
        ("Jenkins Pipeline 配置", "自动化", TaskPriority.HIGH, TaskStatus.TODO, 12, 15, []),
        ("参数化测试数据管理", "自动化", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 16, 35, []),
        ("测试结果自动入库", "自动化", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 20, 40, []),
    ],
    4: [  # HDD 长稳
        ("制定长稳测试规范", "PM", TaskPriority.HIGH, TaskStatus.TODO, 16, 30, []),
        ("20TB HDD 1000h 读写测试", "测试执行", TaskPriority.HIGH, TaskStatus.BACKLOG, 80, 60, []),
        ("22TB HDD 1000h 读写测试", "测试执行", TaskPriority.HIGH, TaskStatus.BACKLOG, 80, 65, []),
        ("掉电一致性测试方案", "可靠性测试", TaskPriority.URGENT, TaskStatus.BACKLOG, 24, 45, []),
        ("坏道增长趋势分析", "TSE", TaskPriority.MEDIUM, TaskStatus.BACKLOG, 12, 55, []),
    ],
}


# Group -> member indices mapping (populated during seeding)
group_members: dict[str, list[int]] = {}


def pick_member(group: str) -> int:
    """Pick a random member index from the given group."""
    return random.choice(group_members[group])


async def seed():
    # Reset DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # ── Admin ──
        admin = User(
            username="admin", email="admin@teampilot.com",
            hashed_password=hash_password("admin123"),
            full_name="系统管理员", role=UserRole.ADMIN,
        )
        db.add(admin)

        # ── Team Members ──
        user_objs: list[User] = []
        for i, m in enumerate(TEAM):
            u = User(
                username=m["username"],
                email=f"{m['username']}@teampilot.com",
                hashed_password=PASSWORD,
                full_name=m["full_name"],
                role=m["role"],
            )
            db.add(u)
            user_objs.append(u)
            group_members.setdefault(m["group"], []).append(i)
        await db.flush()

        all_users = [admin] + user_objs

        # ── Skills ──
        skill_objs: list[Skill] = []
        for name, cat in SKILLS:
            s = Skill(name=name, category=cat)
            db.add(s)
            skill_objs.append(s)
        await db.flush()

        # Assign skills to users based on group
        skill_map = {
            "PM": ["项目管理", "需求分析", "测试方案设计"],
            "TSE": ["存储协议分析", "S.M.A.R.T 分析", "Linux 系统", "Python", "Shell", "NVMe 测试"],
            "测试执行": ["FIO", "vdbench", "IOmeter", "Linux 系统", "Windows Server", "缺陷分析"],
            "自动化": ["Python", "Pytest", "Robot Framework", "Jenkins CI", "Selenium", "Shell"],
            "性能测试": ["FIO", "vdbench", "基准测试", "性能调优", "压力测试", "CrystalDiskMark"],
            "兼容性测试": ["Windows Server", "VMware ESXi", "Linux 系统", "HDD 兼容性"],
            "可靠性测试": ["数据一致性校验", "掉电保护测试", "长稳测试", "FIO"],
            "测试环境": ["Linux 系统", "VMware ESXi", "Shell", "Jenkins CI"],
        }
        skill_name_to_obj = {s.name: s for s in skill_objs}
        for i, m in enumerate(TEAM):
            grp = m["group"]
            for sname in skill_map.get(grp, []):
                if sname in skill_name_to_obj:
                    db.add(UserSkill(
                        user_id=user_objs[i].id,
                        skill_id=skill_name_to_obj[sname].id,
                        proficiency=random.randint(2, 5),
                    ))
        await db.flush()

        # ── Projects ──
        proj_objs: list[Project] = []
        for p in PROJECTS:
            # Pick a PM as owner
            pm_idx = random.choice(group_members["PM"])
            proj = Project(
                name=p["name"], description=p["desc"], status=p["status"],
                owner_id=user_objs[pm_idx].id,
                start_date=p["start"], end_date=p["end"],
            )
            db.add(proj)
            proj_objs.append(proj)
        await db.flush()

        # Add all relevant members to each project
        for proj in proj_objs:
            added_ids = set()
            for u in user_objs:
                if random.random() < 0.6:  # 60% chance each person is in the project
                    if u.id not in added_ids:
                        db.add(ProjectMember(
                            project_id=proj.id, user_id=u.id,
                            role_in_project=ProjectRole.MEMBER,
                        ))
                        added_ids.add(u.id)
            # Ensure owner is member
            if proj.owner_id not in added_ids:
                db.add(ProjectMember(
                    project_id=proj.id, user_id=proj.owner_id,
                    role_in_project=ProjectRole.LEAD,
                ))
        await db.flush()

        # ── Tasks ──
        sort_counter = 0
        for proj_idx, tasks_def in TASKS_BY_PROJECT.items():
            proj = proj_objs[proj_idx]
            for tdef in tasks_def:
                title, grp, priority, status, hours, deadline_offset, subtasks = (
                    tdef[0], tdef[1], tdef[2], tdef[3], tdef[4], tdef[5], tdef[6] if len(tdef) > 6 else []
                )
                assignee_idx = pick_member(grp)
                completed_at = NOW + timedelta(days=deadline_offset - 2) if status == TaskStatus.DONE else None
                sort_counter += 1
                parent = Task(
                    project_id=proj.id, title=title, status=status, priority=priority,
                    assignee_id=user_objs[assignee_idx].id,
                    creator_id=proj.owner_id,
                    estimated_hours=Decimal(str(hours)),
                    deadline=NOW + timedelta(days=deadline_offset),
                    completed_at=completed_at,
                    sort_order=sort_counter,
                )
                db.add(parent)
                await db.flush()

                # Add progress logs for non-backlog tasks
                if status in (TaskStatus.DONE, TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW):
                    pct = 100 if status == TaskStatus.DONE else random.randint(20, 80)
                    db.add(TaskProgress(
                        task_id=parent.id, user_id=user_objs[assignee_idx].id,
                        progress_pct=pct,
                        note=f"{'任务已完成' if pct == 100 else '正在进行中，进度 ' + str(pct) + '%'}",
                        hours_spent=Decimal(str(round(hours * pct / 100 * random.uniform(0.8, 1.3), 1))),
                    ))

                # Subtasks
                for st in subtasks:
                    st_title, st_grp, st_pri, st_status, st_hours, st_deadline_offset = st
                    st_assignee_idx = pick_member(st_grp)
                    st_completed = NOW + timedelta(days=st_deadline_offset - 1) if st_status == TaskStatus.DONE else None
                    sort_counter += 1
                    sub = Task(
                        project_id=proj.id, title=st_title, status=st_status, priority=st_pri,
                        assignee_id=user_objs[st_assignee_idx].id,
                        creator_id=proj.owner_id,
                        parent_task_id=parent.id,
                        estimated_hours=Decimal(str(st_hours)),
                        deadline=NOW + timedelta(days=st_deadline_offset),
                        completed_at=st_completed,
                        sort_order=sort_counter,
                    )
                    db.add(sub)
                    await db.flush()
                    if st_status in (TaskStatus.DONE, TaskStatus.IN_PROGRESS):
                        pct = 100 if st_status == TaskStatus.DONE else random.randint(30, 70)
                        db.add(TaskProgress(
                            task_id=sub.id, user_id=user_objs[st_assignee_idx].id,
                            progress_pct=pct, note="进度更新",
                            hours_spent=Decimal(str(round(st_hours * pct / 100, 1))),
                        ))

        await db.flush()

        # ── AI Config ──
        db.add(AIConfig(
            id=1,
            api_base_url="https://coding.dashscope.aliyuncs.com/v1",
            api_key_encrypted="sk-sp-6adb827d9edc42f1869069beca5cb246",
            model_name="qwen3.5-plus",
            max_tokens=4096,
            temperature=Decimal("0.7"),
        ))

        await db.commit()
        print(f"[OK] Seeded: 1 admin + {len(user_objs)} members, {len(skill_objs)} skills, {len(proj_objs)} projects")
        print(f"[OK] Login: admin/admin123 or any member with password: 123456")


if __name__ == "__main__":
    asyncio.run(seed())
