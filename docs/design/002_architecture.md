# Design Doc 002：AI+PBL Agent 架构（Web UI + FastAPI + LangGraph）

**状态**：Implemented  
**日期**：2026-02-20  
**作者**：AI+PBL Team

---

## 1. 背景与目标
PBL（项目式学习）课程设计需要大量专业知识与结构化产出。本项目希望通过 Agent + HITL 机制，帮助教师快速生成并校验课程组件，同时提供可视化、可编辑的 Web UI，提升实际可用性与交付效率。

目标：
- Web UI 作为主入口（资源管理器 / 预览与编辑 / 状态与交互）
- HITL 逐步确认，组件可控可追溯
- 编辑上游内容时自动级联失效下游
- 缺少 API Key 或模型慢响应时前端有明确提示

---

## 2. 总体架构

```
┌──────────────────────────┐        ┌──────────────────────────┐
│ Web UI (React + Vite)    │  REST  │ FastAPI Server           │
│ Explorer / Preview/Edit  │ <----> │ Session + API            │
│ Status / Feedback        │        │ Virtual Files Projection │
└─────────────┬────────────┘        └─────────────┬────────────┘
              │                                   │
              ▼                                   ▼
       Markdown Viewer                      LangGraph Workflow
       (edit + save)                        (reasoning/action)
```

---

## 3. 前端（React + Vite）

### 3.1 三栏布局
- 左：资源管理器（中文命名 + 指定顺序）
  - 课程总览固定置顶：`course_design.md`
  - 其余组件顺序：情景 → 驱动问题 → 问题链 → 活动 → 实验
  - 按“已完成 / 进行中 / 未开始”分区
- 中：Markdown 预览与编辑
  - 预览：`react-markdown` + `remark-gfm`（支持表格）
  - 编辑：同页切换，样式接近预览
  - 浏览按钮触发保存并回到预览
  - 预览流式仅对每个文件首次打开生效（伪流式）
- 右：状态与交互
  - 会话设置表格 → 点击开始折叠为单行摘要
  - 接受 / 拒绝（拒绝仅进入反馈输入）
  - Enter 提交反馈并重生成（Shift+Enter 换行）

### 3.2 会话设置
字段：年级、时长、课堂模式、主题、知识点、课堂背景、需求描述、HITL、级联  
- 知识点与主题在前端合并成 `topic` 发送
- 需求描述作为 `user_input` 发送（可为空）
- 会话开始后，设置区折叠为单行摘要

---

## 4. 后端（FastAPI）

### 4.1 API 设计
- `POST /api/sessions`：创建会话并生成首个组件（若有输入）
- `GET /api/sessions/{session_id}`：获取当前会话与虚拟文件投影
- `POST /api/sessions/{session_id}/actions`：`accept | regenerate | reset`
- `PUT /api/sessions/{session_id}/files`：保存编辑内容并级联失效下游
- `GET /api/sessions/{session_id}/export`：导出课程 JSON

### 4.2 Session 存储
- 内存字典：`session_id -> {config, state}`
- `config` 记录会话参数；`state` 记录工作流状态

### 4.3 静态资源与 CORS
- `web/dist` 存在时由 FastAPI 直接托管 SPA
- 开发环境允许 `http://127.0.0.1:5173`

### 4.4 API Key 保护
- 缺少 `DEEPSEEK_API_KEY` 时返回可读错误，前端显示提示

---

## 5. LangGraph 工作流

### 5.1 节点结构
- `reasoning_node`
  - 解析用户输入、加载知识库、生成上下文摘要
  - 规划组件生成顺序（action_sequence）
- `action_node`
  - 调用 `generate_*` 工具生成组件
  - 进入 HITL 等待确认

### 5.2 HITL 循环
- 生成组件 → 进入 `await_user`
- `accept`：锁定组件并进入下一步
- `regenerate`：根据反馈重生成（默认级联）

---

## 6. 核心状态模型（AgentState 关键字段）
- 输入与设置：`user_input`, `topic`, `grade_level`, `duration`, `classroom_mode`, `classroom_context`
- 工作流：`action_sequence`, `current_component`, `await_user`, `pending_component`
- 课程设计：`course_design`
- 进度与有效性：`design_progress`, `component_validity`, `locked_components`
- 追踪：`observations`, `action_inputs`

---

## 7. 虚拟文件投影
后端将 `AgentState` 投影为虚拟文件列表：
- 课程组件：
  - `course/scenario.md`
  - `course/driving_question.md`
  - `course/question_chain.md`
  - `course/activity.md`
  - `course/experiment.md`
  - `course/course_design.md`
  - `course/course_design.json`（只读，当前 UI 隐藏）
- 调试文件（当前 UI 不显示）：
  - `debug/context_summary.md`
  - `debug/observations.log`
  - `debug/action_inputs.json`

状态规则（后端统一计算）：`pending / locked / invalid / valid / empty`

---

## 8. 输出归档
每次生成完成后，后端会将当前课程组件写入 `output/` 目录：
- 路径：`output/<session_id>/gen_XXX_YYYYMMDD_HHMMSS/`
- 输出内容：`scenario.md`、`driving_question.md`、`question_chain.md`、`activity.md`、`experiment.md`、`course_design.md`

---

## 9. 级联规则
上游组件变更（编辑或重生成）后下游失效：
- `scenario` → `driving_question / question_chain / activity / experiment`
- `driving_question` → `question_chain / activity / experiment`
- `question_chain` → `activity / experiment`
- `activity` → `experiment`

说明：
- 手动编辑 Markdown 文件默认不级联，下游由用户在反馈中授权重生成

---

## 10. 自动起点路由
`determine_start_from` 规则：
1) 若提供 seed 组件，优先使用  
2) 明确标记（如 `scenario:` 或中文提示）优先  
3) LLM 路由器判断（JSON 输出 `start_from`）  
4) 回退到 `topic`

---

## 11. 启动方式
`main.py` 默认启动 Web UI：
- `python main.py`：启动 FastAPI 并自动打开浏览器  
- `python main.py --cli`：CLI 模式  
- `python main.py --ui streamlit`：旧版 Streamlit（保留）

---

## 12. 错误与可用性
- LLM 失败或无 API Key：返回 `error`，前端可见
- 前端显示“思考中”动画

---

## 13. 关键文件
- `server/app.py`
- `server/models.py`
- `server/session_store.py`
- `server/state_ops.py`
- `server/virtual_files.py`
- `graph/workflow.py`
- `nodes/reasoning_node.py`
- `nodes/action_node.py`
- `tools/generate_*.py`
- `web/src/App.tsx`
- `web/src/styles.css`
- `main.py`
