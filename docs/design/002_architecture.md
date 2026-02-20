# Design Doc 002: AI+PBL Agent 

**状态**: Draft
**日期**: 2026-02-19
**作者**: AI+PBL Team

---

## 1. 背景与目标

### 1.1 问题陈述
PBL（项目式学习）课程设计需要专业的教育学知识，教师往往需要大量时间才能设计出高质量的 PBL 课程方案。

### 1.2 目标
构建一个 AI Agent，能够根据用户输入（主题、年级、时长），自动生成完整的 PBL 课程方案，包括：
- 教学场景
- 驱动问题
- 问题链
- 活动设计
- 实验设计

### 1.3 MVP 范围
- 轻量级实现，无 RAG 依赖
- 通过结构化 Prompt + 预置知识库实现
- 3 天内可交付可用原型

---
2. 架构设计（更新）
2.1 技术栈（小幅调整）
模块	技术方案	说明
Agent 编排	LangGraph	管理状态机 + HITL 循环
LLM 调用	LangChain + DeepSeek API	支持多次生成 / 重生成
上下文注入	结构化 Prompt + 预置 JSON 知识库	本地文件，零外部依赖
交互方式	CLI（HITL）	逐组件 y/n 确认
NEXT_COMPONENT   REGENERATE_COMPONENT
                  ↓
              PREVIEW_COMPONENT

3.3 拒绝后的级联规则（默认行为）

拒绝当前组件 ⇒ 当前组件重生成

默认级联失效并重生成所有下游组件

可选：用户明确声明“只改当前，不动后面”

4. 任意起点机制（新增章节）
4.1 支持的起点
起点	是否允许空输入	规则
scenario	✅	模型可完全生成
topic	✅	模型可生成
activity	❌	必须提供 ≥1 句已有内容
experiment	❌	必须提供 ≥1 句已有内容
4.2 起点判定逻辑
if start_from in [activity, experiment]:
    if no user-provided content:
        prompt user to fallback to full generation

5. 数据结构（更新）
5.1 AgentState（新增 HITL / 起点字段）
class AgentState(TypedDict):
    # 用户输入
    user_input: str
    start_from: str                  # scenario | topic | activity | experiment

    # 起点内容（可选）
    provided_components: dict        # 用户提供的已有组件内容

    # 课程设计
    course_design: dict              # 当前版本课程方案
    locked_components: list          # 已确认（accepted）的组件

    # 进度与有效性
    design_progress: dict
    component_validity: dict         # VALID / INVALID

    # 上下文
    context_summary: str
    knowledge_snippets: dict

    # 规划
    action_sequence: list
    current_component: str

    # HITL
    user_feedback: dict              # 针对某组件的修改意见

6. 核心节点设计（调整）
6.1 推理节点（reasoning_node）

新增职责：

校验 start_from 合法性

合并用户提供的已有组件内容

从指定起点规划 action_sequence

6.2 执行节点 → HITL Action Loop

原 action_node 升级为 可中断、可回退、可重生成的循环节点

职责：

针对 current_component 调用 generate_*

输出预览

等待用户确认（y / n）

n ⇒ 进入编辑反馈 + 重生成

y ⇒ 锁定组件，进入下一个

7. 工具集设计（原则不变，语义升级）

每个 generate_* 工具必须满足：

幂等性：同输入 + 不同 feedback ⇒ 可重生成

可局部重跑：不依赖未来组件

显式依赖声明：便于级联失效

8. 端到端流程示例（更新）

用户输入：

--start-from activity
已有活动：学生分组观察路口交通标志并分类


系统行为：

校验起点合法（activity + 有内容）

锁定 activity 初始版本

从 activity → experiment 进入 HITL 循环

用户拒绝 experiment

仅重生成 experiment

完成

9. MVP 升级后的核心价值
能力	说明
HITL	人是 gate，不是 reviewer
任意起点	真实贴合教师工作流
可回退	每个组件都是 checkpoint
工程可控	状态机清晰，易调试
可演进	天然支持 Agent 化 / 多轮
10. 后续演进（更新）

新增方向：

UI 化：CLI → Web 风格