# TeamPilot 接入 DeepSeek Harness 插件方案

## 结论与范围

推荐保留 TeamPilot 的 FastAPI、数据库、Web 管理界面和业务权限，把 AI 编排改成原生 DSH 插件。DSH 负责模型、Agent 循环、会话、工具调度、取消和运行时审批；插件负责读取业务上下文、生成建议及调用经授权的业务接口。不在插件中再实现一个 Agent 循环，也不修改 DSH 上游源码。

本方案已进入实施：原生插件位于 `plugins/packages/dsh-teampilot`，使用单包 Host/Client 双入口和独立 TeamPilot Agent 预设。用户后续确认删除旧 AI，已取消旧 AI 回退开关；当前安装、草稿流程与验证边界以 [插件说明](../plugins/packages/dsh-teampilot/README.md) 为准。下文保留原始设计的扩展路线，未列为已验证的项目不能视为验收完成。

## 已核实的上游接口

2026-10-05 本机安装阶段改为适配官方 npm `latest` 的 `0.2.0-rc.2`；`dsh-teampilot@0.1.1` 增加原生 bundle 声明，可由插件管理器安装和启用。以下 alpha 源码核查记录是最初设计依据，不是当前安装目标。

核查日期：2026-10-05；源码提交：`5badb15009ae1756c3afe0ae0cef1faafc290ccc`；`@deepseek-ai/dsh-base` 源码版本：`0.2.1-alpha.1`。该版本处于预览阶段，应锁定兼容提交，不能直接承诺兼容所有后续版本。

| 扩展点 | 官方源码依据 | 用途 |
| --- | --- | --- |
| Cordis `apply(ctx)`、`inject`、`ctx.effect()` | [插件教程](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/user/develop/basic/index.md) | 服务依赖、装载与卸载清理 |
| `ctx.tools.register(defineTool(...))` | [工具契约](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/cookbook/adding-a-tool.md) | 参数验证、结构化返回、取消信号、工具呈现 |
| `tools/pre-execute`、`ctx.approval`、`ctx.tools.guard()` | [扩展参考](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/cookbook/extension-cookbook.md) | DSH 的允许、拒绝、询问及最终拒绝策略 |
| Session Controller 的 create/prompt/follow 与取消操作 | [Session Controller](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/packages/api/session-controller/README.md) | 创建或继续 DSH 会话，消费原生历史和控制状态 |
| `@Remote`、`@RemoteScope`、生成的 `ctx.remote` 接口 | [API Gateway](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/api-gateway.md) | Host 与插件 Client 的受控通信；不是任意 HTTP `/agent/run` 接口 |
| `dsh.client`、`ctx.slots.inject/register()` | [Client Modules](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/subsystems/client-modules.md)、[Slots](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/subsystems/slots.md) | 原生 React 客户端扩展及工具结果卡片 |
| Connection 的 Host/Origin 校验和浏览器认证 | [Web Server](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/subsystems/web-server.md) | 本地 Host 的认证边界；自行添加 HTTP 路由不能绕开此层 |

现有 Vue 组件不能直接作为 React Slot 组件注册。把网站放进 iframe 只解决展示，不会自动接入 Agent、业务审批或会话生命周期。

## 推荐架构

```text
用户的 DSH Web / Desktop
  原生 DSH Agent + Session + 模型配置
       |
  dsh-teampilot 插件
    Host: TeamPilot API 客户端、账号绑定、业务工具、草稿流程
    Client: 项目选择、建议预览、审批结果、会话入口
       | 用户自己的短期凭证；HTTPS 或受限本机连接
  TeamPilot FastAPI
    JWT / RBAC / 字段校验 / 权重与进度 / 会签 / 事务 / 审计
       |
  PostgreSQL / SQLite
```

TeamPilot 独立 Web 继续可用。第一阶段从 DSH 内使用 Agent，不让独立 Web 直接连接一个未经设计的公司级 DSH 网关。官方本地 Web 默认是回环服务，不能据此推断它已具备多租户服务端隔离。团队部署建议每位使用者运行自己的 DSH，连接同一个 TeamPilot 后端。

## 包和所有权

实现采用 `dsh-teampilot` 单包，提供独立 Host、Client、preset 和生成 Remote 入口，避免过早拆分。

```text
plugins/packages/dsh-teampilot/
  src/host/index.ts                   # 服务、业务工具、审批门槛、Agent 预设
  src/host/api.ts                     # 固定服务地址、超时、内存凭证、取消
  src/host/preset.ts                  # 业务工具白名单
  src/shared/types.ts                 # 浏览器安全的 Remote 类型
  src/client/index.tsx                # 原生 Slot、登录、项目、会话、草稿审阅
  scripts/build.mjs                   # 官方 Typert 生成和双端构建
  tests/host.test.mjs                 # 真实工具运行时与 HTTP 边界测试
```

模型密钥由 DSH 管理，不复制到 TeamPilot 插件。DSH 会话 ID 与业务项目 ID 是关联信息，不是新的任务真相源。TeamPilot 保留业务审计，DSH 保留 Agent 会话；两边不互相覆盖进度或重复维护工具调度状态。

## 功能迁移

| 当前功能 | 插件路径 | 写入策略 |
| --- | --- | --- |
| 工时预估、派单建议 | 读取任务、人员技能及负荷，交给 DSH Agent 分析 | 仅输出建议；用户采纳后调用现有编辑接口 |
| 项目和任务树生成 | Agent 输出结构化草稿，插件与后端分别验证 | 新草稿提交事务复用项目、任务服务，不调用旧 AI 路由 |
| 群消息进展导入 | Agent 匹配项目/人员/任务，对歧义先澄清 | 审阅逐条进度差异，提交复用进度服务；跨项目拆成独立草稿 |
| 日报、风险、复盘 | 分页读取有界上下文，由 Agent 生成报告 | 初期不自动写任务、不自动发送邮件 |
| 会签建议 | Agent 给出证据和疑点 | 建议不等于会签；会签仍由有权限的人单独操作 |

工具命名建议：`teampilot_list_projects`、`teampilot_get_task_tree`、`teampilot_get_workload`、`teampilot_propose_plan`、`teampilot_propose_progress`、`teampilot_get_draft`。初期不提供通用任意 URL 请求工具、不提供可批量删除或无确认会签的工具。

每个工具用 `defineTool` 的参数 DSL 和 `output.schema` 声明结构化输入输出；`execute` 返回 canonical JSON，`output.render` 才提供模型文本。请求接入 `exec.signal`，对数据量、响应字节、调用次数和时长设上限。PTC 模式会通过正常工具管线调用这些工具，不另造一条绕过权限的执行通道。

## 账号、审批与并发

1. 绑定真实 TeamPilot 用户，不使用共享管理员 Token。凭证只留在 Host 的受限存储，禁止注入 Prompt、返回工具结果或写日志。
2. DSH 的工具审批是运行时控制；TeamPilot RBAC 是业务授权。两者同时成立才允许写入，不能把 DSH 的 Allow 当作管理员权限。
3. 已增加 `dsh_drafts` 和 `/api/v1/integrations/dsh` 接口，存放作者、规范化 payload hash、项目 revision、有效期、状态及结果。模型只能创建和读取草稿；批准仅暴露给原生 Client，确认凭据仅存 Host；提交工具还需 DSH 原生审批。
4. 提交时后端重新检查权限、当前任务、父子归属、日期、权重及会签门槛。通过预期版本防止覆盖别人的新进展；通过幂等键防止断网重试重复新增任务或进展。版本冲突返回需重新预览，而不是静默覆盖。
5. 禁止凭 Prompt 中的“用户已经确认”通过审批。DSH 的通用 Shell 能力不构成业务授权，业务预设应收紧不必要的工具；同一主机上的高权限操作者不是这套审批的防御对象。
6. 旧 AI 已移除，不提供自动回退。错误、冲突或失效审批停止敏感操作，业务 Web 的手动操作继续可用。

## UI 与会话接入

首期直接使用 DSH 原生对话和通用工具卡片，保留外部 TeamPilot Web 链接，成本最低。第二期通过原生 Slot 加入项目选择、审批入口和结果卡片；优先扩展 list Slot 的新 ID，不覆盖 root、现有对话或单值 Slot。

插件 Client 通过 Session Controller 的公开契约发起或继续会话，读取 follow/history 和控制状态；不要自己拼模型请求。Host 的自定义业务方法若需给 Client 调用，使用生成的 Typert Remote 契约及独立插件的显式 contribution 装配，不能假设注册一个 Host 服务就自动出现在所有 `ctx.remote` 命名空间。此装配必须先做无上游修改的最小验证。

任务面板可后续用 React 重写必要部分；不建议首期全面重写 Vue。若临时保留嵌入页，必须继续使用独立业务认证和严谨的消息来源校验，它不作为 Agent 或审批的安全边界。

## 实施顺序与验收

1. **只读 PoC**：锁定 DSH 提交，注册两个只读工具，真实账号读取项目和任务，原生 Agent 生成报告。验证登录撤销、超时、取消、分页、插件卸载和断网失败。
2. **草稿阶段**：支持计划和群进展草稿，验证歧义、未知用户/任务、模型输出非法值及注入文本；不写业务数据。
3. **受控写入**：补齐后端草稿、单次审批、幂等和版本检查，验证双用户冲突、重复提交、取消后提交、过期授权及完整审计。
4. **原生 UI**：验证 Slot、Client manifest、生成 Remote 装配、会话重连/回放，兼容 Web 与 Desktop 后再切换日常入口。
5. **替换旧 AI**：按用户追加确认直接删除旧调用和 Vue AI 界面，独立业务 Web 保留。真实模型连续任务、Electron Desktop 和 PostgreSQL 并发仍需单独验收，不由构建或 SQLite 测试替代。

验收要求：不修改 DSH 上游；Agent 状态仅由 DSH 拥有；越权和未经确认写入全部拒绝；三等分权重不误报（容差仍为 0.01）；新增子任务重新打开已完成祖先并保留会签历史；同一提交最多写入一次；取消/断网/重连不造成假成功；无凭证或敏感完整人员资料泄漏到日志及模型上下文。

成本取舍：只读工具成本最低且先验证最关键的接口假设；原生审批 UI 与后端草稿有明显开发成本，但它们决定写入是否可靠。全面搬迁数据库和 Vue 前端到 DSH 成本最高，也会破坏现有多用户业务边界，本项目不推荐。
