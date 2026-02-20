# Design Doc 002: AI+PBL Agent 架构（Web UI + FastAPI）

**状态**: Implemented  
**日期**: 2026-02-20  
**作者**: AI+PBL Team

---

## 1. 背景与目标
PBL（项目式学习）课程设计需要大量专业知识与结构化产出。本项目希望通过 Agent + HITL 机制，帮助教师快速生成并校验课程组件，同时提供可视化、可编辑的 Web UI，提升实际可用性与交付效率。

目标：
- 以 Web UI 为主入口，提供三栏（Explorer / Viewer / 状态与交互）体验
- HITL 逐步确认，确保每个组件可控可追溯
- 编辑上游内容时自动级联失效下游，保证一致性
- 缺少 API Key 或 LLM 慢响应时，UI 有明确反馈

---

## 2. 总体架构

```
┌─────────────────────┐        ┌─────────────────────┐
│  Web UI (React)     │  REST  │   FastAPI Server    │
│  Explorer / Viewer  │ <----> │  Session + API       │
│  Status / Actions   │        │  Virtual Files       │
└─────────┬───────────┘        └─────────┬───────────┘
          │                               │
          │                               │
          ▼                               ▼
   Markdown Viewer                  LangGraph Workflow
   (edit + save)                    (reasoning/action)
```

---

## 3. 核心模块设计（已实现）

### 3.1 Web 前端（React + Vite）
- 三栏布局：左侧 Explorer，中间 Markdown Viewer，右侧状态与交互
- Markdown 渲染：`react-markdown` + `remark-gfm`（支持表格）
- Viewer 编辑模式：点击“编辑”进入编辑态，保存后回写后端
- 一次性问答：右侧在开始前通过输入框完成设置（年级/时长/课堂模式/HITL/级联/主题/背景）
- Pending 信息栏：输入框上方展示当前待确认组件
- 右侧仅显示状态/提示与操作按钮（完成 / 反馈重生成）

### 3.2 FastAPI 服务
- 提供 Session + Action + 文件回写 API：
  - `POST /api/sessions`
  - `GET /api/sessions/{session_id}`
  - `POST /api/sessions/{session_id}/actions`
  - `PUT /api/sessions/{session_id}/files`
  - `GET /api/sessions/{session_id}/export`
- 缺少 `DEEPSEEK_API_KEY` 时，返回清晰错误信息供前端展示
- 生产环境：若存在 `web/dist`，直接挂载静态资源
- 开发环境：启用 CORS 允许 `http://127.0.0.1:5173`

### 3.3 Session & 状态机
- Session 以内存字典存储（`session_id -> {config, state}`）
- `AgentState` 维护：
  - `course_design`、`design_progress`、`component_validity`
  - `await_user`、`pending_component`、`pending_preview`
  - `locked_components`、`observations` 等
- HITL 机制：
  - `pending_component` 生成后进入待确认状态
  - 接收 `accept / regenerate` 决策后继续推进

### 3.4 虚拟文件模型
- 课程组件映射为虚拟文件：
  - `course/scenario.md`
  - `course/driving_question.md`
  - `course/question_chain.md`
  - `course/activity.md`
  - `course/experiment.md`
  - `course/course_design.md`（整体结果预览）
  - `course/course_design.json`（只读信息）
- Debug 文件：
  - `debug/context_summary.md`
  - `debug/observations.log`
  - `debug/action_inputs.json`
- 状态规则（后端统一计算）：`pending / locked / invalid / valid / empty`

### 3.5 自动起点路由
- `determine_start_from` 自动路由：
  1) 若提供 seed 组件，优先使用（scenario / activity / experiment）
  2) 明确标记（如 `scenario:`、`activity:` 或中文“已有场景”）优先
  3) LLM 路由器判断（JSON 输出 `start_from`）
  4) 回退到 `topic`

### 3.6 级联规则
- 编辑/重生成上游组件会级联失效下游：
  - `scenario` → `driving_question / question_chain / activity / experiment`
  - `driving_question` → `question_chain / activity / experiment`
  - `question_chain` → `activity / experiment`
  - `activity` → `experiment`
- 编辑回写会清空下游并标记 `INVALID`，确保一致性

### 3.7 错误与加载
- LLM 调用失败或无 API Key 时，响应中带 `error` 字段
- 前端显示“思考中…”动画与错误提示，避免白屏

### 3.8 静态资源与 CORS
- `web/dist` 存在时由 FastAPI 直接托管 SPA
- 本地开发使用 Vite + 代理，FastAPI 保留 CORS 兼容

---

## 4. 数据流

1) **创建会话**
   - 前端提交用户输入与设置
   - 后端创建 Session 并生成首个组件（如有输入）

2) **HITL 操作**
   - `accept`：确认当前组件并进入下一步
   - `regenerate`：对目标组件反馈后重生成（默认级联）

3) **编辑回写**
   - Viewer 保存触发 `PUT /files`
   - 后端更新 `course_design` 并级联失效下游

4) **导出**
   - `GET /export` 返回完整课程设计 JSON

---

## 5. 实现清单（对照）
- [x] FastAPI 后端与核心 API 完成
- [x] Web UI 三栏布局与中文文案
- [x] Markdown Viewer（含表格渲染）与编辑回写
- [x] HITL 接受/重生成流程
- [x] 自动起点路由（显式规则 + LLM）
- [x] 级联失效机制
- [x] 错误提示与加载状态
- [x] 静态资源托管与 CORS

---

## 6. 关键文件
- `server/app.py`
- `server/state_ops.py`
- `server/virtual_files.py`
- `server/session_store.py`
- `web/src/App.tsx`
- `web/src/styles.css`
- `main.py`
