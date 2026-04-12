"""Create 3 new verification projects."""
import asyncio
import random
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

from sqlalchemy import select
from app.database import async_session
from app.models.user import User
from app.models.project import Project, ProjectMember, ProjectStatus, ProjectRole
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.task_progress import TaskProgress

NOW = datetime.now(timezone.utc)


async def seed():
    async with async_session() as db:
        res = await db.execute(select(User).where(User.is_active == True))
        all_users = res.scalars().all()
        um = {u.full_name: u for u in all_users}

        def u(name):
            return um.get(name, random.choice(all_users))

        # ═══════════════════════════════════════════════
        # Project 1: NVMe SSD 量产前验证
        # ═══════════════════════════════════════════════
        p1 = Project(
            name="NVMe SSD X2 量产前终验",
            description="X2 系列 NVMe SSD 进入量产前最终验证，覆盖功能、性能、可靠性和兼容性。需在 4 周内完成并输出认证报告。",
            status=ProjectStatus.ACTIVE, owner_id=u("赵磊").id,
            start_date=date(2026, 4, 1), end_date=date(2026, 5, 10),
        )
        db.add(p1)
        await db.flush()
        for n in ["赵磊", "刘洋", "陈飞", "任刚", "魏岚", "贾鑫", "江南", "侯亮", "高芳", "林波"]:
            db.add(ProjectMember(project_id=p1.id, user_id=u(n).id, role_in_project=ProjectRole.MEMBER))
        await db.flush()

        s = 0
        # --- 固件功能测试 ---
        s += 1
        t1 = Task(project_id=p1.id, title="固件功能测试", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.HIGH,
                   assignee_id=u("刘洋").id, creator_id=u("赵磊").id, estimated_hours=Decimal("40"),
                   deadline=NOW + timedelta(days=10), sort_order=s)
        db.add(t1); await db.flush()
        db.add(TaskProgress(task_id=t1.id, user_id=u("刘洋").id, progress_pct=60,
                            note="基础读写命令测试完成，Namespace 管理测试进行中", hours_spent=Decimal("24")))
        for title, st, usr, h in [
            ("NVMe Admin Command 测试", TaskStatus.DONE, "刘洋", 8),
            ("IO Command (Read/Write/Flush)", TaskStatus.DONE, "陈飞", 10),
            ("Namespace 管理测试", TaskStatus.IN_PROGRESS, "刘洋", 8),
            ("Error Injection 测试", TaskStatus.TODO, "陈飞", 6),
            ("Firmware Download 测试", TaskStatus.TODO, "刘洋", 8),
        ]:
            s += 1
            sub = Task(project_id=p1.id, title=title, status=st, priority=TaskPriority.HIGH,
                       assignee_id=u(usr).id, creator_id=u("赵磊").id, parent_task_id=t1.id,
                       estimated_hours=Decimal(str(h)), deadline=NOW + timedelta(days=8), sort_order=s,
                       completed_at=NOW - timedelta(days=2) if st == TaskStatus.DONE else None)
            db.add(sub); await db.flush()
            if st == TaskStatus.DONE:
                db.add(TaskProgress(task_id=sub.id, user_id=u(usr).id, progress_pct=100, note="已完成", hours_spent=Decimal(str(h))))

        # --- 性能基线测试 ---
        s += 1
        t2 = Task(project_id=p1.id, title="性能基线测试", status=TaskStatus.IN_PROGRESS, priority=TaskPriority.HIGH,
                   assignee_id=u("任刚").id, creator_id=u("赵磊").id, estimated_hours=Decimal("32"),
                   deadline=NOW + timedelta(days=14), sort_order=s)
        db.add(t2); await db.flush()
        for title, st, usr, h in [
            ("顺序读写吞吐量测试 (128K)", TaskStatus.DONE, "任刚", 6),
            ("随机 4K IOPS 测试", TaskStatus.IN_PROGRESS, "魏岚", 8),
            ("混合读写模型测试 (OLTP/OLAP)", TaskStatus.TODO, "任刚", 8),
            ("QoS 延迟分布 (P99/P999)", TaskStatus.TODO, "魏岚", 6),
            ("Steady State 稳态性能测试", TaskStatus.BACKLOG, "任刚", 4),
        ]:
            s += 1
            sub = Task(project_id=p1.id, title=title, status=st, priority=TaskPriority.HIGH,
                       assignee_id=u(usr).id, creator_id=u("赵磊").id, parent_task_id=t2.id,
                       estimated_hours=Decimal(str(h)), deadline=NOW + timedelta(days=12), sort_order=s,
                       completed_at=NOW - timedelta(days=1) if st == TaskStatus.DONE else None)
            db.add(sub); await db.flush()
            if st == TaskStatus.DONE:
                db.add(TaskProgress(task_id=sub.id, user_id=u(usr).id, progress_pct=100, note="数据已记录", hours_spent=Decimal(str(h))))

        # --- 兼容性 ---
        s += 1
        t3 = Task(project_id=p1.id, title="平台兼容性验证", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM,
                   assignee_id=u("贾鑫").id, creator_id=u("赵磊").id, estimated_hours=Decimal("24"),
                   deadline=NOW + timedelta(days=20), sort_order=s)
        db.add(t3); await db.flush()
        for title, h in [("Intel Xeon 平台验证", 6), ("AMD EPYC 平台验证", 6), ("ARM 服务器平台验证", 6), ("主流 RAID 卡兼容性", 6)]:
            s += 1
            db.add(Task(project_id=p1.id, title=title, status=TaskStatus.BACKLOG, priority=TaskPriority.MEDIUM,
                        assignee_id=u("贾鑫").id, creator_id=u("赵磊").id, parent_task_id=t3.id,
                        estimated_hours=Decimal(str(h)), deadline=NOW + timedelta(days=18), sort_order=s))
            await db.flush()

        # --- 可靠性 ---
        s += 1
        t4 = Task(project_id=p1.id, title="可靠性与数据保护测试", status=TaskStatus.TODO, priority=TaskPriority.URGENT,
                   assignee_id=u("江南").id, creator_id=u("赵磊").id, estimated_hours=Decimal("48"),
                   deadline=NOW + timedelta(days=25), sort_order=s)
        db.add(t4); await db.flush()
        for title, usr, h in [
            ("异常掉电数据一致性测试", "江南", 12), ("温度循环 (-40~85C) 测试", "江南", 8),
            ("1000 次热插拔测试", "侯亮", 8), ("UBER 误码率测试", "江南", 8),
            ("72h 持续写入寿命测试", "侯亮", 12),
        ]:
            s += 1
            db.add(Task(project_id=p1.id, title=title, status=TaskStatus.BACKLOG, priority=TaskPriority.URGENT,
                        assignee_id=u(usr).id, creator_id=u("赵磊").id, parent_task_id=t4.id,
                        estimated_hours=Decimal(str(h)), deadline=NOW + timedelta(days=23), sort_order=s))
            await db.flush()

        # --- 认证报告 ---
        s += 1
        db.add(Task(project_id=p1.id, title="输出量产认证报告", status=TaskStatus.BACKLOG, priority=TaskPriority.HIGH,
                     assignee_id=u("赵磊").id, creator_id=u("赵磊").id, estimated_hours=Decimal("16"),
                     deadline=NOW + timedelta(days=28), sort_order=s))

        # ═══════════════════════════════════════════════
        # Project 2: 自动化回归测试平台
        # ═══════════════════════════════════════════════
        p2 = Project(
            name="自动化回归测试平台搭建",
            description="搭建 Pytest + Jenkins + Allure 自动化回归平台，实现核心用例每日自动执行和报告推送。",
            status=ProjectStatus.ACTIVE, owner_id=u("孙伟").id,
            start_date=date(2026, 4, 5), end_date=date(2026, 6, 30),
        )
        db.add(p2); await db.flush()
        for n in ["孙伟", "谢健", "邓超", "萧丽", "潘伟", "蒋毅", "龙斌"]:
            db.add(ProjectMember(project_id=p2.id, user_id=u(n).id, role_in_project=ProjectRole.MEMBER))
        await db.flush()

        tasks2 = [
            ("测试框架选型与环境搭建", TaskStatus.DONE, "谢健", 16, -5, [
                ("Pytest + conftest 架构设计", TaskStatus.DONE, "谢健", 6),
                ("Jenkins Master/Slave 部署", TaskStatus.DONE, "龙斌", 6),
                ("Allure 报告服务搭建", TaskStatus.DONE, "邓超", 4),
            ]),
            ("SSD 核心用例自动化", TaskStatus.IN_PROGRESS, "谢健", 40, 20, [
                ("SMART 属性读取自动化", TaskStatus.DONE, "谢健", 6),
                ("FIO 性能测试自动化封装", TaskStatus.DONE, "萧丽", 8),
                ("固件升级自动化脚本", TaskStatus.IN_PROGRESS, "潘伟", 10),
                ("掉电测试自动化 (PDU 控制)", TaskStatus.TODO, "蒋毅", 8),
                ("温度监控自动采集", TaskStatus.BACKLOG, "邓超", 8),
            ]),
            ("HDD 长稳测试自动化", TaskStatus.TODO, "萧丽", 32, 35, [
                ("vdbench 参数化封装", TaskStatus.TODO, "萧丽", 8),
                ("坏道检测自动化", TaskStatus.BACKLOG, "潘伟", 8),
                ("SMART 趋势分析脚本", TaskStatus.BACKLOG, "蒋毅", 8),
                ("异常中断恢复脚本", TaskStatus.BACKLOG, "邓超", 8),
            ]),
            ("CI/CD Pipeline 配置", TaskStatus.TODO, "龙斌", 16, 30, []),
            ("测试报告邮件推送", TaskStatus.BACKLOG, "邓超", 8, 40, []),
            ("用例管理与标签体系", TaskStatus.BACKLOG, "谢健", 12, 45, []),
        ]
        s = 0
        for title, status, usr, hours, dd, subs in tasks2:
            s += 1
            t = Task(project_id=p2.id, title=title, status=status, priority=TaskPriority.HIGH,
                     assignee_id=u(usr).id, creator_id=u("孙伟").id, estimated_hours=Decimal(str(hours)),
                     deadline=NOW + timedelta(days=dd), sort_order=s,
                     completed_at=NOW + timedelta(days=dd - 2) if status == TaskStatus.DONE else None)
            db.add(t); await db.flush()
            if status in (TaskStatus.DONE, TaskStatus.IN_PROGRESS):
                pct = 100 if status == TaskStatus.DONE else 50
                db.add(TaskProgress(task_id=t.id, user_id=u(usr).id, progress_pct=pct, note="进度更新",
                                    hours_spent=Decimal(str(round(hours * pct / 100)))))
            for st_title, st_status, st_usr, st_h in subs:
                s += 1
                sub = Task(project_id=p2.id, title=st_title, status=st_status, priority=TaskPriority.MEDIUM,
                           assignee_id=u(st_usr).id, creator_id=u("孙伟").id, parent_task_id=t.id,
                           estimated_hours=Decimal(str(st_h)), deadline=NOW + timedelta(days=dd - 2), sort_order=s,
                           completed_at=NOW + timedelta(days=dd - 3) if st_status == TaskStatus.DONE else None)
                db.add(sub); await db.flush()
                if st_status == TaskStatus.DONE:
                    db.add(TaskProgress(task_id=sub.id, user_id=u(st_usr).id, progress_pct=100, note="已完成",
                                        hours_spent=Decimal(str(st_h))))

        # ═══════════════════════════════════════════════
        # Project 3: XX银行 POC
        # ═══════════════════════════════════════════════
        p3 = Project(
            name="XX银行 POC 全闪存验证",
            description="为 XX 银行搭建 POC 环境，在其数据中心完成全闪存阵列部署、数据迁移和业务压力测试。预计 2 周驻场。",
            status=ProjectStatus.ACTIVE, owner_id=u("钱华").id,
            start_date=date(2026, 4, 10), end_date=date(2026, 4, 28),
        )
        db.add(p3); await db.flush()
        for n in ["钱华", "杨明", "黄杰", "高芳", "郭宇", "白丽"]:
            db.add(ProjectMember(project_id=p3.id, user_id=u(n).id, role_in_project=ProjectRole.MEMBER))
        await db.flush()

        tasks3 = [
            ("POC 方案设计与评审", TaskStatus.DONE, "钱华", 8, -3),
            ("硬件设备发货与签收", TaskStatus.DONE, "白丽", 4, -1),
            ("存储阵列部署与初始化", TaskStatus.IN_PROGRESS, "杨明", 12, 3),
            ("数据迁移方案验证", TaskStatus.TODO, "黄杰", 16, 7),
            ("OLTP 业务压力测试", TaskStatus.TODO, "高芳", 12, 10),
            ("OLAP 报表查询测试", TaskStatus.TODO, "郭宇", 8, 12),
            ("故障切换演练", TaskStatus.BACKLOG, "杨明", 8, 14),
            ("POC 报告编写与交付", TaskStatus.BACKLOG, "钱华", 8, 16),
        ]
        s = 0
        for title, status, usr, hours, dd in tasks3:
            s += 1
            t = Task(project_id=p3.id, title=title, status=status,
                     priority=TaskPriority.HIGH if dd < 7 else TaskPriority.MEDIUM,
                     assignee_id=u(usr).id, creator_id=u("钱华").id, estimated_hours=Decimal(str(hours)),
                     deadline=NOW + timedelta(days=dd), sort_order=s,
                     completed_at=NOW + timedelta(days=dd - 1) if status == TaskStatus.DONE else None)
            db.add(t); await db.flush()
            if status in (TaskStatus.DONE, TaskStatus.IN_PROGRESS):
                pct = 100 if status == TaskStatus.DONE else 40
                db.add(TaskProgress(task_id=t.id, user_id=u(usr).id, progress_pct=pct, note="进度更新",
                                    hours_spent=Decimal(str(round(hours * pct / 100)))))

        await db.commit()
        print("[OK] Created 3 new projects:")
        print("  1. NVMe SSD X2 量产前终验 (5 大任务 + 19 子任务)")
        print("  2. 自动化回归测试平台搭建 (6 大任务 + 12 子任务)")
        print("  3. XX银行 POC 全闪存验证 (8 个任务)")

asyncio.run(seed())
