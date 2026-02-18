# AI+PBL Agent MVP

基于 LangGraph 的 PBL（项目式学习）课程自动生成系统。

## 功能特性

- 自动解析用户输入，提取主题、年级、时长
- 智能匹配预置知识库，生成上下文摘要
- 生成完整的 PBL 课程方案，包含：
  - 教学场景
  - 驱动问题
  - 问题链
  - 活动设计
  - 实验设计

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入你的 DeepSeek API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```
DEEPSEEK_API_KEY=your_api_key_here
```

### 3. 运行

**命令行模式：**

```bash
python main.py "为初中二年级设计'AI如何识别交通标志'PBL课程，45分钟"
```

**参数模式：**

```bash
python main.py --topic "图像识别" --grade "初中" --duration 45
```

**保存结果到文件：**

```bash
python main.py "为初中设计'语音识别'PBL课程" -o output.json
```

## 项目结构

```
project/
├── main.py                 # 入口文件
├── config.py               # 配置管理
├── requirements.txt        # 依赖清单
│
├── docs/design/            # 设计文档
│   └── 001_initial_architecture.md
│
├── state/
│   └── agent_state.py      # AgentState 定义
│
├── nodes/
│   ├── reasoning_node.py   # 推理与规划节点
│   └── action_node.py      # 执行节点
│
├── tools/
│   ├── generate_scenario.py
│   ├── generate_driving_question.py
│   ├── generate_activity.py
│   └── generate_experiment.py
│
├── prompts/
│   ├── scenario.txt
│   ├── driving_question.txt
│   ├── activity.txt
│   └── experiment.txt
│
├── knowledge/
│   └── knowledge_base.json # 预置知识库
│
└── graph/
    └── workflow.py         # LangGraph 工作流
```

## 工作流

```
用户输入 → 推理节点 → 执行节点 → 课程输出
              ↓           ↓
         解析输入     调用工具
         生成上下文   更新状态
         匹配知识库   循环执行
         规划动作
```

## 技术栈

- **LangGraph**: Agent 状态管理与工作流编排
- **LangChain**: LLM 调用与 Prompt 管理
- **DeepSeek API**: 大语言模型服务

## Design Docs

设计文档记录了项目的架构演进：

- [001_initial_architecture.md](docs/design/001_initial_architecture.md) - 初始架构设计

## License

MIT License
