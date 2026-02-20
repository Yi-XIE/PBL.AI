# AI+PBL Agent MVP

基于 LangGraph 的 PBL（项目式学习）课程自动生成系统。默认提供 Web UI（FastAPI + React）。

## 功能亮点
- 自动解析用户输入并生成完整课程方案：scenario / driving question / question chain / activity / experiment
- HITL 逐步确认：每个组件生成后需确认或反馈重生成
- 上游编辑默认级联：修改 scenario 等上游会标记下游失效
- VSCode 风格三栏界面：Explorer / Markdown Viewer / 状态与交互

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 API Key
复制 `.env.example` 为 `.env` 并填写 DeepSeek API Key：
```bash
cp .env.example .env
```

```
DEEPSEEK_API_KEY=your_api_key_here
```

### 3. 运行 Web UI（默认）
```bash
python main.py
```

- 若 `web/dist` 不存在，请先构建前端：
```bash
cd web
npm install
npm run build
```

- 开发模式：
```bash
# 终端 A：启动后端
python main.py

# 终端 B：启动前端开发服务器
cd web
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。

### 4. CLI 模式（可选）
```bash
python main.py --cli
python main.py "为初中二年级设计 'AI如何识别交通标志' PBL课程，45分钟"
python main.py --topic "图像识别" --grade "初中" --duration 45
```

### 5. Legacy Streamlit UI（可选）
```bash
python main.py --ui streamlit
# 或
streamlit run ui/app_streamlit.py
```

## Web UI 使用方式（简要）
- 右侧先进行一次性问答（年级、时长、课堂模式、HITL、级联、主题、课堂背景），在输入框一次性回答
- 左侧 Explorer 显示虚拟文件树（包含 `course_design.md`）
- 中间 Markdown Viewer 支持预览和“编辑”回写，保存后自动级联
- 右侧状态区提示“思考中…/完成/需要反馈”，可执行完成/反馈重生成

## 项目结构
```
project/
├─ main.py
├─ server/           # FastAPI 后端与 Session 状态
├─ web/              # React + Monaco + Markdown Viewer 前端
├─ graph/            # LangGraph 工作流
├─ nodes/            # 推理与动作节点
├─ state/            # AgentState 定义
├─ tools/            # 生成工具
├─ prompts/          # Prompt 模板
└─ knowledge/        # 预置知识库
```

## 设计文档
- `docs/design/001_initial_architecture.md`
- `docs/design/002_architecture.md`

## License
MIT License
