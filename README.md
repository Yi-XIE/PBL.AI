# PBL Studio V4

面向 PBL（Project‑Based Learning）的课程方案生成与迭代系统。  
当前版本以 **LLM 强制接入** 为前提，通过 **Chat 入口** 决定任务入口（`scenario` 或 `tool_seed`），并用候选‑选择‑反馈‑再生成‑最终确认的流程逐步产出课程方案。

---

## Quick Start

```bash
python -m venv .venv
. .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m uvicorn api.app:app --reload --port 8000
```

打开调试 UI：  
`http://127.0.0.1:8000/debug`

---

## LLM 配置（必须）

系统默认要求接入 LLM。若未配置 key，API 会返回 503。
服务启动会自动加载项目根目录的 `.env`。

支持 OpenAI 兼容配置（也可使用 DeepSeek 兼容接口）：

**通用：**
- `LLM_REQUIRED=true`（默认 true）
- `LLM_MODEL`（可选）
- `LLM_TEMPERATURE`（可选）
- `LLM_API_KEY`（可选）
- `LLM_BASE_URL`（可选）

**OpenAI：**
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` / `OPENAI_API_BASE`（可选）
- `OPENAI_MODEL`（可选）

**DeepSeek：**
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`（可选）
- `DEEPSEEK_MODEL`（可选）

---

## 系统流程

核心状态流转：

```
generation → selection → feedback → regenerate → finalize
```

设计原则：
- 每个阶段用户都可以介入，不会被自动跳过
- 只对用户选中的候选进行校验与最终确认
- `iteration_count` 在每一次完整的用户决策循环中只递增一次
- `regenerate` 后旧冲突会被清理/重新计算，不残留

---

## 调试 UI（/debug）

三栏布局：
- **左栏：对话**（Chat/Copilot 风格）：包含系统、LLM、用户消息
- **中栏：候选**：显示候选标题与内容预览，用户选择
- **右栏：课程方案**：由已选候选拼接得到的最终方案

说明：
- Chat 输入默认走 `/api/chat`
- 任务创建后自动订阅 SSE 事件（`decision`, `candidates`, `message`, `task_updated`）
- 右侧 **Course Plan** 使用 `/api/tasks/{id}/plan` 聚合已选内容

---

## API 概览

### Chat 入口
`POST /api/chat`

Request:
```json
{
  "session_id": "optional",
  "message": "user text",
  "task_id": "optional"
}
```

Response:
```json
{
  "session_id": "...",
  "status": "ask" | "ready",
  "assistant_message": "...",
  "entry_point": "scenario" | "tool_seed" | null,
  "entry_data": { ... } | null,
  "task_id": "optional"
}
```

### 创建任务
`POST /api/tasks`

```json
{ "entry_point": "scenario", "scenario": "..." }
```
或
```json
{ "entry_point": "tool_seed", "tool_seed": { ... } }
```

### 任务动作
`POST /api/tasks/{id}/action`

```json
{
  "action_type": "select_candidate" | "regenerate_candidates" | "provide_feedback" | "finalize_stage" | "resolve_conflict",
  "payload": { ... }
}
```

### 任务详情
`GET /api/tasks/{id}`

### 进度
`GET /api/tasks/{id}/progress`

### 课程方案聚合
`GET /api/tasks/{id}/plan`

### SSE 事件
`GET /api/tasks/{id}/events`

事件包括：
- `decision`
- `candidates`
- `message`
- `task_updated`

---

## 数据模型（摘要）

- **Task**：核心任务对象，包含 `artifacts`、`conflicts`、`messages`
- **Message**：对话消息（SSE `message` 事件）
- **Candidate**：各阶段生成候选
- **StageArtifact**：每阶段的候选与状态

---

## 目录结构

```
api/               FastAPI 路由与静态 UI
adapters/          LLM / tracing 适配
core/              核心模型与类型
engine/            状态机与 reducer
generators/        各阶段 LLM 生成器
services/          orchestrator / SSE / chat / plan 等
validators/        校验与冲突检测
```

---

## Tests

```bash
pytest
```

测试已使用 Fake LLM 以避免真实调用。

---

## Notes

- 若出现 `LLM not configured`：请检查环境变量与 base_url。
- UI 只展示课程方案聚合，不再显示冲突面板或 Stage‑level 操作按钮。
