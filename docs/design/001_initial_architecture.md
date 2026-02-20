# Design Doc 001: AI+PBL Agent 初始架构

**状态**: Draft
**日期**: 2026-02-18
**作者**: JasonXie

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

## 2. 架构设计

### 2.1 技术栈

| 模块 | 技术方案 | 说明 |
|------|---------|------|
| Agent 编排 | LangGraph | 管理状态流转与循环逻辑 |
| LLM 调用 | LangChain + DeepSeek API | 统一调用 DeepSeek 模型 |
| 上下文注入 | 结构化 Prompt 模板 + 预置 JSON 知识库 | 本地文件存储，零外部依赖 |
| 开发语言 | Python | 利用 LangChain/LangGraph 生态 |

### 2.2 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      User Input                              │
│         "为初中二年级设计'AI交通标志识别'PBL课程，45分钟"    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Reasoning Node                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 解析用户输入 │→│ 生成上下文  │→│ 匹配知识库片段      │  │
│  │             │  │ _summary    │  │ knowledge_snippets  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│              ┌─────────────────────┐                        │
│              │ 规划 action_sequence │                        │
│              └─────────────────────┘                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Action Node                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  顺序执行 generate_* 工具                             │   │
│  │  - generate_scenario                                  │   │
│  │  - generate_driving_question                          │   │
│  │  - generate_activity                                  │   │
│  │  - generate_experiment                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Course Output                             │
│              完整的 PBL 课程方案（5 组件）                   │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 工作流状态机

```
START → reasoning_node → action_node → [完成判断]
                                         ↓
                              未完成 → 循环回 action_node
                              已完成 → END
```

---

## 3. 数据结构

### 3.1 AgentState 全局状态

```python
class AgentState(TypedDict):
    # 用户输入区域
    user_input: str           # 原始请求
    topic: str                # 课程主题
    grade_level: str          # 年级（小学/初中/高中）
    duration: int             # 课时（分钟）

    # 课程设计区域
    course_design: dict       # 包含5个组件的完整课程方案

    # 进度追踪
    design_progress: dict     # 各组件完成状态标记

    # 智能上下文
    context_summary: str      # 推理节点生成的定制化上下文摘要

    # 规划信息
    thought: str              # 推理过程
    action_sequence: list     # 待执行的动作列表
    action_inputs: dict       # 每个动作的输入参数
    observations: list        # 动作执行结果

    # 知识缓存
    knowledge_snippets: dict  # 从预置知识库匹配的规则片段
```

### 3.2 预置知识库结构

```json
{
  "grade_rules": {
    "小学": "用故事/游戏导入；单环节≤10分钟；材料安全无尖锐物；语言具象化",
    "初中": "含小组讨论；单环节≤15分钟；可引入基础概念；关联生活经验",
    "高中": "支持深度探究；可含简单代码体验；强调伦理思辨"
  },
  "topic_templates": {
    "图像识别": "生活场景：交通标志/水果分类/手写数字；类比：'AI眼睛学认路'",
    "自然语言处理": "聚焦情感分析/智能客服；活动：设计班级聊天机器人",
    "数据伦理": "案例：推荐算法偏见；讨论：'AI会歧视吗？'"
  },
  "safety_constraints": [
    "严禁使用尖锐/易燃/有毒材料",
    "实验需在教师监督下进行",
    "符合《义务教育课程方案》安全规范"
  ]
}
```

---

## 4. 核心节点设计

### 4.1 推理节点 (reasoning_node)

**职责**：
1. 解析用户输入（提取 topic、grade_level、duration）
2. 生成 context_summary（定制化上下文摘要）
3. 匹配 knowledge_snippets（从预置知识库）
4. 规划 action_sequence（动作序列）

**示例 context_summary 输出**：
```
面向初中二年级（具象思维为主），45分钟需含1个动手环节。
主题关联学生过马路经验，用'AI眼睛学认路'类比，避免算法术语。
```

### 4.2 执行节点 (action_node)

**职责**：
1. 根据 action_sequence 调用对应 generate_* 工具
2. 每个工具自动融合：预置规则 + Few-shot + context_summary + 用户参数
3. 更新 course_design 和 design_progress
4. 处理工具执行结果

---

## 5. 工具集设计

### 5.1 generate_scenario
**输入**：topic, grade_level, context_summary, knowledge_snippets
**Prompt 构成**：[角色锚定] + [年级规则] + [主题模板] + [Few-shot示例] + [用户参数]

### 5.2 generate_driving_question
**输入**：scenario, context_summary
**Prompt 构成**：[驱动问题黄金法则] + [示例对比] + [当前场景]

### 5.3 generate_activity
**输入**：driving_question, duration, knowledge_snippets
**Prompt 构成**：[课时分配规则] + [活动设计模板] + [安全约束]

### 5.4 generate_experiment
**输入**：topic, grade_level, knowledge_snippets
**Prompt 构成**：[材料安全清单] + [简易实验范式] + [教室可行性]

---

## 6. Prompt 设计原则

1. **模板文件化**：每工具独立 Prompt 模板文件（.txt）
2. **Few-shot 示例**：内置 2-3 个高质量示例
3. **明确约束**：如"初中避免抽象术语""实验材料限教室常见物品"
4. **强制格式**：如"问题链：1. ... 2. ..."

---

## 7. 端到端流程示例

**用户输入**：
```
"为初中二年级设计'AI如何识别交通标志'PBL课程，45分钟"
```

**推理节点处理**：
- 生成 context_summary：初中二年级具象思维为主，45分钟需含动手环节
- 匹配 knowledge_snippets：grade_rules["初中"] + topic_templates["图像识别"]
- 规划动作：["generate_scenario", "generate_driving_question", "generate_activity", "generate_experiment"]

**执行节点处理**：
- 顺序执行 4 个生成工具
- 每步自动继承上下文
- 输出完整课程方案

**用户反馈处理**：
```
"实验部分太复杂，简化一下"
```
- 识别"修改实验"意图
- 仅重规划 ["generate_experiment"]
- 更新状态

---

## 8. MVP 优势

| 维度 | 优势说明 |
|------|---------|
| 极速交付 | 无需搭建 RAG 链路，3 天内完成核心功能 |
| 成本极低 | 仅消耗 DeepSeek API 费用 |
| 效果可控 | Prompt + Few-shot + 知识库三重保障 |
| 调试友好 | 所有上下文可见，问题定位快速 |
| 平滑演进 | 后续加 RAG：仅需替换 knowledge_snippets 来源 |

---

## 9. 后续演进方向

1. **RAG 集成**：将预置知识库替换为向量检索
2. **多轮对话**：支持更自然的课程修改交互
3. **评估体系**：自动评估生成课程的质量
4. **模板扩展**：支持更多学科和主题模板

---

## 10. 参考资源

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Documentation](https://python.langchain.com/)
- [DeepSeek API Documentation](https://platform.deepseek.com/docs)
