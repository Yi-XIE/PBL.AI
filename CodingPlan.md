AI+PBL Agent MVP 详细架构设计（无 RAG 版）
一、核心目标
构建轻量级 MVP：聚焦“动态生成高质量 PBL 课程方案”核心能力，通过结构化 Prompt 工程 + 预置知识库 + 智能上下文提炼实现精准内容生成，完全移除 RAG 依赖，确保 3 天内可交付可用原型。
二、技术栈精简版
模块	技术方案	说明
Agent 编排	LangGraph	管理状态流转与循环逻辑
LLM 调用	LangChain + DeepSeek API	统一调用 deepseek或qwen-plus 模型
上下文注入	结构化 Prompt 模板库 + 预置 JSON 知识库	本地文件存储，零外部依赖
开发语言	Python	利用 LangChain/LangGraph 生态

三、全局状态设计（AgentState）
区域	字段	说明
用户输入	user_input, topic, grade_level, duration	原始请求与课程元数据
课程设计	course_design（含5个组件）	场景/问题/问题链/活动/实验
进度追踪	design_progress	各组件完成状态标记
智能上下文	context_summary	新增：推理节点生成的定制化上下文摘要
规划信息	thought, action_sequence, action_inputs, observations	ReAct 批量规划所需字段
知识缓存	knowledge_snippets	新增：从预置知识库匹配的规则片段
四、核心节点功能
1. 推理与规划节点（reasoning_node）
• 核心增强：增加“上下文智能提炼”能力 
  • 解析用户输入（如“初中二年级”“45分钟”“交通标志”）
  • 动态生成 context_summary：
“面向初中二年级（具象思维为主），45分钟需含1个动手环节。主题关联学生过马路经验，用‘AI眼睛学认路’类比，避免算法术语。”
  • 匹配预置知识库：
根据 grade_level 提取年级规则（如“初中：单环节≤15分钟”）
根据 topic 匹配主题模板（如“图像识别→交通标志/水果分类”）
→ 存入 knowledge_snippets
  • 规划动作序列：仅包含生成类动作（如 ["generate_scenario", "generate_driving_question"]）
• 输出更新：thought, action_sequence, action_inputs, context_summary, knowledge_snippets
2. 执行节点（action_node）
• 简化逻辑：仅调用 generate_* 工具序列
• 参数增强：将 context_summary 与 knowledge_snippets 注入每个动作的输入参数
• 结果归集：更新 course_design 与 design_progress
五、工具集（纯生成型）
工具	输入增强	Prompt 核心构成
generate_scenario	topic, grade_level, context_summary, knowledge_snippets	[角色锚定] + [年级规则] + [主题模板] + [Few-shot示例] + [用户参数]
generate_driving_question	scenario, context_summary	[驱动问题黄金法则] + [示例对比] + [当前场景]
generate_activity	driving_question, duration, knowledge_snippets	[课时分配规则] + [活动设计模板] + [安全约束]
generate_experiment	topic, grade_level, knowledge_snippets	[材料安全清单] + [简易实验范式] + [教室可行性]
Prompt 设计原则： 
• 每工具独立 Prompt 模板文件（.txt） 
• 内置 2-3 个高质量 Few-shot 示例 
• 明确约束（如“初中避免抽象术语”“实验材料限教室常见物品”） 
• 强制输出格式（如“问题链：1. ... 2. ..."）
六、预置知识库设计（本地 JSON 文件）
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
• 加载方式：Agent 启动时一次性读入内存
• 使用时机：reasoning_node 中按需匹配注入
七、工作流编排
1. 启动：初始化 AgentState，加载预置知识库
2. 推理阶段： 
  • 分析用户输入
  • 生成 context_summary
  • 匹配 knowledge_snippets
  • 规划纯生成动作序列
3. 执行阶段： 
  • 顺序调用 generate_* 工具
  • 每个工具自动融合：预置规则 + Few-shot + context_summary + 用户参数
4. 终止判断：检查 course_design 完整性 → 完成则输出，未完成则循环
5. 用户反馈处理：识别修改意图（如“简化实验”）→ 仅重规划需修改组件
八、端到端流程示例
1. 用户输入：
“为初中二年级设计‘AI如何识别交通标志’PBL课程，45分钟”
2. 推理节点处理：
  • 生成 context_summary：
“初中二年级具象思维为主，45分钟需含动手环节。关联过马路经验，用‘AI眼睛学认路’类比，避免卷积神经网络等术语。”
  • 匹配 knowledge_snippets：
grade_rules["初中"] + topic_templates["图像识别"]
  • 规划动作：["generate_scenario", "generate_driving_question", "generate_activity", "generate_experiment"]
3. 执行节点处理：
  • generate_scenario：Prompt = [角色] + [初中规则] + [图像识别模板] + [示例] + context_summary → 输出场景
  • 后续工具依次生成，每步自动继承上下文
  • 最终输出完整课程方案
4. 用户反馈：
“实验部分太复杂，简化一下”
→ 推理节点识别“修改实验” → 规划 ["generate_experiment"] → 仅重生成实验部分 → 更新状态
九、MVP 核心优势
维度	优势说明
极速交付	无需搭建 RAG 链路，3 天内完成核心功能开发与测试
成本极低	仅消耗 DeepSeek API 费用，无阿里云服务开销
效果可控	Prompt 模板 + Few-shot + 知识库三重保障，生成质量稳定
聚焦验证	直接验证“教师是否认可生成内容”这一核心假设
平滑演进	后续加 RAG 时：仅需将 knowledge_snippets 替换为检索结果，架构零改动
调试友好	所有上下文可见（context_summary/knowledge_snippets），问题定位快速
十、MVP 交付清单
1. Prompt 模板库（4个工具 × 精细化模板）
2. 预置知识库 JSON（年级规则/主题模板/安全约束）
3. LangGraph 工作流（reasoning_node + action_node）
4. DeepSeek API 集成（统一调用封装）
5. 测试用例集（覆盖小学/初中/高中典型场景）