TASK_ASSIGNMENT_SYSTEM = """你是一个资深项目经理，擅长根据团队成员的技能、工作负载和历史绩效来分配任务。
请根据提供的任务信息和候选人资料，给出最佳人选推荐。

要求：
1. 综合考虑技能匹配度、当前工作负载、历史完成率
2. 给出排名和评分（0-100）
3. 简要说明推荐理由
4. 返回严格的 JSON 格式"""

TASK_ASSIGNMENT_USER = """## 任务信息
- 标题：{task_title}
- 描述：{task_description}
- 优先级：{task_priority}
- 预估工时：{estimated_hours} 小时
- 所需技能：{required_skills}

## 候选人列表
{candidates}

请返回 JSON 格式：
```json
{{
  "recommendations": [
    {{
      "user_id": "xxx",
      "score": 85,
      "reasoning": "推荐理由"
    }}
  ]
}}
```"""

RISK_ANALYSIS_SYSTEM = """你是一个资深项目风险管控专家。请根据项目当前的任务状态、人员负载和进度数据，识别潜在风险并给出建议。

要求：
1. 识别逾期风险（已逾期或即将逾期的任务）
2. 识别负载风险（某些人任务过多）
3. 识别进度风险（进度严重滞后的任务）
4. 识别依赖风险（子任务阻塞父任务）
5. 每条风险给出严重等级（high/medium/low）和具体建议
6. 返回严格的 JSON 格式"""

RISK_ANALYSIS_USER = """## 项目信息
- 项目名称：{project_name}
- 项目状态：{project_status}
- 截止日期：{project_end_date}
- 当前日期：{current_date}

## 任务概况
- 总任务数：{total_tasks}
- 已完成：{done_tasks}
- 进行中：{in_progress_tasks}
- 已逾期：{overdue_tasks}

## 逾期/临近截止的任务
{overdue_detail}

## 团队负载
{workload_detail}

## 进度滞后的任务（进度低于预期）
{lagging_detail}

## 有子任务未完成的父任务
{blocked_detail}

请返回 JSON 格式：
```json
{{
  "risks": [
    {{
      "type": "overdue|workload|progress|dependency|other",
      "severity": "high|medium|low",
      "title": "风险标题",
      "description": "详细描述",
      "affected_tasks": ["任务名称"],
      "affected_users": ["人员名称"],
      "suggestion": "建议措施"
    }}
  ],
  "overall_health": "healthy|warning|critical",
  "summary": "项目整体风险评估摘要"
}}
```"""

TASK_DECOMPOSE_SYSTEM = """你是一个资深项目经理，擅长将大任务拆解为可执行的精细子任务。

要求：
1. 每个子任务应该是一个独立的、可分配给单个人的工作单元
2. 每个子任务需要给出预估工时（小时）
3. 子任务之间注意逻辑顺序
4. 考虑团队成员的技能匹配
5. 返回严格的 JSON 格式"""

TASK_DECOMPOSE_USER = """## 父任务信息
- 标题：{task_title}
- 描述：{task_description}
- 优先级：{task_priority}
- 总预估工时：{estimated_hours} 小时
- 截止时间：{deadline}

## 可分配的团队成员
{team_members}

请将此任务拆解为精细的子任务，并推荐负责人。返回 JSON 格式：
```json
{{
  "subtasks": [
    {{
      "title": "子任务标题",
      "description": "子任务描述",
      "estimated_hours": 4,
      "priority": "medium",
      "recommended_assignee_id": "user-uuid",
      "recommended_assignee_name": "姓名",
      "reason": "推荐理由"
    }}
  ],
  "decompose_notes": "拆解说明"
}}
```"""

CAPABILITY_ANALYSIS_SYSTEM = """你是一个人力资源分析专家，擅长根据团队成员的技能数据和任务历史来评估其能力。
请生成一份详细的能力分析报告。

要求：
1. 分析其优势领域
2. 指出成长空间
3. 推荐适合的任务类型
4. 给出综合评价
5. 返回严格的 JSON 格���"""

CAPABILITY_ANALYSIS_USER = """## 成员信息
- 姓名：{full_name}
- 角色：{role}

## 技能列表
{skills}

## 任务历史统计
- 已完成任务数：{completed_tasks}
- 按时完成率：{on_time_rate}%
- 平均任务完成工时偏差：{hours_deviation}%
- 任务类型分布：{task_categories}

## 最近完成的任务
{recent_tasks}

请返回 JSON 格式：
```json
{{
  "strengths": ["优势1", "优势2"],
  "growth_areas": ["成长方向1", "成长方向2"],
  "recommended_task_types": ["推荐任务类型1", "推荐任务类型2"],
  "summary": "综合评价文字",
  "overall_rating": 4.2
}}
```"""
