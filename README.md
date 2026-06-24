# start-work：Codex 多 Agent 协作开发 Skill

`start-work` 是一个用于 Codex App 的项目级多 Agent 协作开发 skill。它把当前会话作为 Manager，并复用长期 Developer / Reviewer 独立 Codex 线程，让开发任务按照“派工、实现、主会话检查、验收、修复、再验收”的闭环推进。

这个 skill 的核心目标不是简单地“多开几个会话”，而是让多 Agent 协作有明确身份、共享 roster、可追踪台账、事件驱动 handoff，以及可验证的验收循环。

## 适用场景

- 需要 Manager / Developer / Reviewer 分工协作的软件开发任务。
- 希望每个项目只初始化一组长期 Agent 会话，而不是每个任务重复创建线程。
- 希望 Developer 完成后直接发消息交回 Manager，Manager 检查后再直接发给 Reviewer。
- 希望 Reviewer 发现阻断问题时能直接发回 Developer，同时单独抄送 Manager。
- 希望把协作状态、消息、验收结论保存在项目本地，但不污染 Git 提交。

小任务不一定需要启用完整流程，Manager 可以直接处理。

## 核心流程

```text
用户需求
  -> Manager 制定工作单
  -> Developer 实现
  -> Manager 检查 diff / 测试
  -> Reviewer 审查
  -> Reviewer accepted 或发回 Developer 修复
  -> Developer 修复后交回 Manager
  -> Manager 再检查并重新发 Reviewer
  -> 无阻断问题后交付
```

该流程是事件驱动的：默认不要求 Manager 持续轮询其他线程，而是由当前阶段的 Agent 在完成后主动用线程消息发送 handoff。直接 `codex-thread` 模式要求 Manager / Developer / Reviewer 都有真实 thread id；只有 Manager callback 时只能作为手动 relay fallback。

## 项目级长期团队

每个项目维护一份长期团队 roster：

```text
<repo>/.agent-work/start-work/team/
  team.json
  team.md
  standing-developer.md
  standing-reviewer.md
  roster-update.md
```

团队角色：

- `M`：Manager，当前用户会话，负责方向、工作单、台账、集成检查和最终交付。
- `D1`：Developer，长期开发线程，负责实现和修复。
- `R1`：Reviewer，长期验收线程，默认只读，负责审查和接受。

`team.json` 是线程 ID、角色、handoff route 和 ack 状态的本地事实来源。Developer 和 Reviewer 必须确认当前 roster 后，才能开始任务。

## 每个任务的运行台账

每个开发任务创建一个独立 run ledger：

```text
<repo>/.agent-work/start-work/runs/<run-id>/
  coordination.md
  run.json
  events.jsonl
  messages/
  artifacts/
  snapshots/
```

其中：

- `coordination.md`：Manager 维护的任务总台账。
- `run.json`：机器可读的 run 元数据。
- `events.jsonl`：事件流。
- `messages/`：跨线程消息正文。
- `artifacts/`：审查报告、验证摘要等结果。
- `snapshots/`：任务开始时的 Git 状态快照。

`.agent-work/` 默认写入本地 `.git/info/exclude`，不会修改项目 `.gitignore`。

## 安装

把仓库克隆到 Codex 个人 skills 目录：

```powershell
git clone https://github.com/FengYing1314/start-cooperation-agent.git C:\Users\admin\.codex\skills\start-work
```

如果你的 `CODEX_HOME` 不同，请放到对应的 `skills/start-work` 目录。

## 初始化团队

在目标项目中，Manager 先确认项目规则和必读文档，然后创建或确认长期 Developer / Reviewer Codex 线程。

初始化 team：

```bash
python3 <skill-dir>/scripts/init_team.py --repo <repo-root> \
  --manager-thread-id <manager-thread-id> \
  --developer-thread-id <developer-thread-id> \
  --reviewer-thread-id <reviewer-thread-id> \
  --project-doc AGENTS.md
```

如果 Manager 没有稳定 thread id，可以记录 callback 作为手动 relay fallback，但不能用于直接 `codex-thread` run：

```bash
python3 <skill-dir>/scripts/init_team.py --repo <repo-root> \
  --manager-callback "<manager-callback>" \
  --developer-thread-id <developer-thread-id> \
  --reviewer-thread-id <reviewer-thread-id>
```

随后把生成的文件发送给对应线程：

- `team/standing-developer.md` 发给 Developer。
- `team/standing-reviewer.md` 发给 Reviewer。

收到 ack 后记录：

```bash
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role D1
python3 <skill-dir>/scripts/ack_team.py --repo <repo-root> --role R1
```

如果 roster 后续更新，ack 会回到 pending，需要重新发送 `roster-update.md` 并再次记录确认。

## 开始任务

创建新的 run ledger：

```bash
python3 <skill-dir>/scripts/init_run.py --repo <repo-root> --slug <work-slug> --request "<用户需求>"
```

`init_run.py` 会强制检查：

- team 已初始化；
- direct `codex-thread` 模式下 Manager / Developer / Reviewer 都有 thread id；
- D1 和 R1 已确认当前 roster；
- run ledger 已创建；
- `.agent-work/` 已加入本地 Git exclude。

如果任一条件不满足，脚本会失败并给出明确修复提示。

## 记录事件

使用 `append_event.py` 记录消息、状态推进、验证结果和审查结果：

```bash
python3 <skill-dir>/scripts/append_event.py \
  --run-dir <repo>/.agent-work/start-work/runs/<run-id> \
  --kind message \
  --actor M \
  --to D1 \
  --summary "Send work order" \
  --run-status developer_running \
  --body-file <message-file>
```

事件 ID 会自动生成，例如 `M-001`、`D1-001`、`R1-001`。脚本会拒绝重复 ID，避免覆盖历史记录。

## 文件结构

```text
start-work/
  SKILL.md
  agents/
    openai.yaml
  references/
    codex-thread-mode.md
    protocol.md
    roles.md
    templates.md
  scripts/
    init_team.py
    ack_team.py
    init_run.py
    append_event.py
```

## 设计原则

- 项目级长期团队，而不是任务级临时团队。
- 三方共享同一 roster，thread id 变化必须广播并重新 ack。
- Manager 拥有团队台账和任务台账。
- Developer 只处理被分配的实现和修复。
- Reviewer 默认只读，不绕过 Manager 的集成检查直接最终接受。
- Reviewer 可以把阻断问题发回 Developer，但必须抄送 Manager。
- Manager 不以持续轮询为默认控制方式。
- 同一阻断问题连续多轮无法解决时，应停止循环并向用户说明卡点。

## 校验

基础校验：

```bash
python3 -m py_compile scripts/init_team.py scripts/ack_team.py scripts/init_run.py scripts/append_event.py scripts/test_start_work.py
python3 scripts/test_start_work.py
python3 <skill-creator-dir>/scripts/quick_validate.py <skill-dir>
```

建议在临时 Git 仓库中额外验证：

- 未初始化 team 时 `init_run.py` 会失败。
- 未记录 D1 / R1 ack 时 `init_run.py` 会失败。
- callback-only Manager 在 direct `codex-thread` 模式下 `init_run.py` 会失败。
- roster 更新后必须重新 ack。
- run ledger 能继承最新 team roster。
- `append_event.py --run-status` 能推进任务状态。

## 许可证

当前仓库未声明开源许可证。使用或分发前请根据项目需要补充许可证文件。
