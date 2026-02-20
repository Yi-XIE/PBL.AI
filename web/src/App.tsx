import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  AgentState,
  Candidate,
  Message,
  SessionResponse,
  Task,
  VirtualFile,
  VirtualFilesPayload,
} from "./types";

type Settings = {
  topic: string;
  knowledge_point: string;
  grade_level: string;
  duration: number;
  classroom_mode: string;
  classroom_context: string;
  hitl_enabled: boolean;
  cascade_default: boolean;
  multi_option: boolean;
  request: string;
  start_from: string;
  seed_text: string;
};

const DEFAULT_SETTINGS: Settings = {
  topic: "",
  knowledge_point: "",
  grade_level: "初中",
  duration: 80,
  classroom_mode: "normal",
  classroom_context: "",
  hitl_enabled: true,
  cascade_default: true,
  multi_option: true,
  request: "",
  start_from: "topic",
  seed_text: "",
};

const COURSE_ORDER = [
  "course/course_design.md",
  "course/scenario.md",
  "course/driving_question.md",
  "course/question_chain.md",
  "course/activity.md",
  "course/experiment.md",
];

const COMPONENT_ORDER = COURSE_ORDER.filter((path) => path !== "course/course_design.md");

const STAGE_LABELS: Record<string, string> = {
  scenario: "课程情境设计",
  driving_question: "驱动问题设计",
  question_chain: "问题链构建",
  activity: "学习活动设计",
  experiment: "探究与实验设计",
};

const FILE_LABELS: Record<string, string> = {
  "course/course_design.md": "课程总览",
  "course/scenario.md": "情境",
  "course/driving_question.md": "驱动问题",
  "course/question_chain.md": "问题链",
  "course/activity.md": "活动",
  "course/experiment.md": "实验",
};

const MODE_LABELS: Record<string, string> = {
  normal: "常规",
  no_device: "无设备",
  computer_lab: "机房",
};

const statusColor: Record<string, string> = {
  pending: "var(--accent)",
  locked: "var(--good)",
  invalid: "var(--danger)",
  valid: "var(--good)",
  empty: "var(--muted)",
  info: "var(--muted)",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "进行中",
  locked: "已完成",
  valid: "已完成",
  invalid: "未开始",
  empty: "未开始",
  info: "信息",
};

function requiredStages(startFrom?: string): string[] {
  return ["scenario", "driving_question", "question_chain", "activity", "experiment"];
}

function getStageLabel(stage: string): string {
  return STAGE_LABELS[stage] || stage || "暂无";
}

function buildProgressText(stage: string, startFrom?: string): string {
  if (!stage) return "";
  const required = requiredStages(startFrom);
  const index = required.indexOf(stage);
  if (index < 0) return "";
  return `${index + 1} / ${required.length}`;
}

function buildTaskProgress(task: Task | null, stage: string): string {
  if (!task || !stage) return "";
  const stages = task.stages || [];
  const index = stages.indexOf(stage);
  if (index < 0) return "";
  return `${index + 1} / ${stages.length}`;
}

function componentFromPath(path?: string | null): string | null {
  if (!path) return null;
  if (path.endsWith("scenario.md")) return "scenario";
  if (path.endsWith("driving_question.md")) return "driving_question";
  if (path.endsWith("question_chain.md")) return "question_chain";
  if (path.endsWith("activity.md")) return "activity";
  if (path.endsWith("experiment.md")) return "experiment";
  return null;
}

function cascadeTargets(component: string): string[] {
  switch (component) {
    case "scenario":
      return ["driving_question", "question_chain", "activity", "experiment"];
    case "driving_question":
      return ["question_chain", "activity", "experiment"];
    case "question_chain":
      return ["activity", "experiment"];
    case "activity":
      return ["experiment"];
    default:
      return [];
  }
}

function deriveCurrentStage(state: AgentState | null): string {
  if (!state) return "";
  if (state.await_user && state.pending_component) {
    return state.pending_component || "";
  }
  const progress = state.design_progress || {};
  const required = requiredStages(state.start_from);
  for (const stage of required) {
    if (!progress[stage]) {
      return stage;
    }
  }
  return "";
}

function isComplete(state: AgentState | null) {
  if (!state) return false;
  const progress = state.design_progress || {};
  const startFrom = state.start_from || "topic";
  const required = requiredStages(startFrom);
  return required.every((key) => progress[key]);
}

function buildMarkdown(file: VirtualFile | null) {
  if (!file) return "";
  const content = file.content ?? "";
  if (!content.trim()) {
    return "_暂无内容_";
  }
  if (file.language === "markdown") {
    return content;
  }
  const lang = file.language || "";
  return `\`\`\`${lang}\n${content}\n\`\`\``;
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch (err) {
      // ignore json errors
    }
    throw new Error(detail);
  }
  return response.json();
}

function displayFileName(file: VirtualFile) {
  return FILE_LABELS[file.path] || file.path.split("/").pop() || file.path;
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(() => {
    return localStorage.getItem("session_id");
  });
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [setupForm, setSetupForm] = useState<Settings>(DEFAULT_SETTINGS);
  const [state, setState] = useState<AgentState | null>(null);
  const [virtualFiles, setVirtualFiles] = useState<VirtualFilesPayload | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [feedbackText, setFeedbackText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [pendingSave, setPendingSave] = useState<{
    path: string;
    content: string;
    component: string;
    cascadeTargets: string[];
  } | null>(null);
  const [showSavePrompt, setShowSavePrompt] = useState(false);
  const [displayMarkdown, setDisplayMarkdown] = useState("");
  const [feedbackMode, setFeedbackMode] = useState(false);
  const [showSettingsDetails, setShowSettingsDetails] = useState(false);
  const [task, setTask] = useState<Task | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [localMessages, setLocalMessages] = useState<Message[]>([]);

  const lastPendingRef = useRef<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const editRef = useRef<HTMLTextAreaElement | null>(null);
  const streamedRef = useRef<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const { courseDesignFile, courseSections } = useMemo(() => {
    const files = virtualFiles?.files || [];
    const courseFiles = files.filter(
      (file) =>
        file.path.startsWith("course/") &&
        file.path !== "course/course_design.json"
    );
    const courseDesign = courseFiles.find((file) => file.path === "course/course_design.md") || null;
    const orderMap = new Map(COMPONENT_ORDER.map((path, index) => [path, index]));
    const componentFiles = courseFiles.filter((file) => orderMap.has(file.path));
    const sortByOrder = (a: VirtualFile, b: VirtualFile) =>
      (orderMap.get(a.path) ?? 999) - (orderMap.get(b.path) ?? 999);

    const completed = componentFiles
      .filter((file) => ["valid", "locked"].includes(file.status))
      .sort(sortByOrder);
    const inProgress = componentFiles
      .filter((file) => file.status === "pending")
      .sort(sortByOrder);
    const notStarted = componentFiles
      .filter((file) => ["empty", "invalid"].includes(file.status))
      .sort(sortByOrder);

    return {
      courseDesignFile: courseDesign,
      courseSections: [
        { key: "completed", title: "已完成", files: completed },
        { key: "in_progress", title: "进行中", files: inProgress },
        { key: "not_started", title: "未开始", files: notStarted },
      ],
    };
  }, [virtualFiles]);

  const currentFile = useMemo(() => {
    return virtualFiles?.files.find((file) => file.path === selectedPath) || null;
  }, [selectedPath, virtualFiles]);

  const renderedMarkdown = buildMarkdown(currentFile);
  const combinedMessages = useMemo(() => {
    const all = [...messages, ...localMessages];
    return all.sort((a, b) => (a.created_at ?? 0) - (b.created_at ?? 0));
  }, [messages, localMessages]);

  useEffect(() => {
    if (!inputRef.current) return;
    inputRef.current.style.height = "auto";
    inputRef.current.style.height = `${inputRef.current.scrollHeight}px`;
  }, [feedbackText]);

  useEffect(() => {
    if (!currentFile) return;
    if (isEditing) return;
    setEditValue(currentFile.content ?? "");
  }, [currentFile?.path, isEditing]);

  useEffect(() => {
    if (!editRef.current) return;
    editRef.current.style.height = "auto";
    editRef.current.style.height = `${editRef.current.scrollHeight}px`;
  }, [editValue]);

  useEffect(() => {
    if (!currentFile || isEditing) {
      setDisplayMarkdown(renderedMarkdown);
      return;
    }
    const key = currentFile.path;
    if (streamedRef.current.has(key)) {
      setDisplayMarkdown(renderedMarkdown);
      return;
    }
    streamedRef.current.add(key);
    const content = renderedMarkdown;
    if (!content || content.length < 80) {
      setDisplayMarkdown(content);
      return;
    }
    let index = 0;
    const step = Math.max(2, Math.floor(content.length / 400));
    let active = true;
    setDisplayMarkdown("");
    const timer = window.setInterval(() => {
      if (!active) return;
      index = Math.min(content.length, index + step);
      setDisplayMarkdown(content.slice(0, index));
      if (index >= content.length) {
        window.clearInterval(timer);
      }
    }, 16);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [renderedMarkdown, currentFile?.path, isEditing]);

  useEffect(() => {
    if (!messagesEndRef.current) return;
    messagesEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [combinedMessages]);

  const applySession = (payload: SessionResponse) => {
    setState(payload.state);
    setVirtualFiles(payload.virtual_files);
    setTask(payload.task ?? null);
    setMessages(payload.messages ?? []);
    if (payload.error) {
      setError(payload.error);
    } else {
      setError(null);
    }

    const pending = payload.state.pending_component || payload.state.current_component || null;
    if (pending && pending !== lastPendingRef.current) {
      const defaultPath = payload.virtual_files?.selected_default;
      if (defaultPath) {
        setSelectedPath(defaultPath);
      }
      lastPendingRef.current = pending;
    } else if (!selectedPath && payload.virtual_files?.selected_default) {
      setSelectedPath(payload.virtual_files.selected_default);
    }
  };

  const handleNewSession = () => {
    localStorage.removeItem("session_id");
    setSessionId(null);
    setState(null);
    setVirtualFiles(null);
    setSelectedPath(null);
    setSettings(DEFAULT_SETTINGS);
    setSetupForm(DEFAULT_SETTINGS);
    setFeedbackText("");
    setError(null);
    setLoading(false);
    setIsEditing(false);
    setEditValue("");
    setDisplayMarkdown("");
    setFeedbackMode(false);
    setShowSettingsDetails(false);
    setPendingSave(null);
    setShowSavePrompt(false);
    setTask(null);
    setMessages([]);
    setLocalMessages([]);
    lastPendingRef.current = null;
    streamedRef.current.clear();
  };

  const loadSession = async (id: string) => {
    setTask(null);
    setMessages([]);
    setLocalMessages([]);
    try {
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${id}`);
      setSessionId(payload.session_id);
      localStorage.setItem("session_id", payload.session_id);
      applySession(payload);
    } catch (err) {
      localStorage.removeItem("session_id");
      setSessionId(null);
      setState(null);
      setVirtualFiles(null);
      setTask(null);
      setMessages([]);
      setLocalMessages([]);
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    if (sessionId) {
      loadSession(sessionId);
    }
  }, []);

  const handleStart = async () => {
    setTask(null);
    setMessages([]);
    setLocalMessages([]);
    setLoading(true);
    setError(null);
    try {
      const knowledge = setupForm.knowledge_point.trim();
      const baseTopic = setupForm.topic.trim();
      const mergedTopic = knowledge
        ? baseTopic
          ? `${baseTopic}｜知识点：${knowledge}`
          : `知识点：${knowledge}`
        : baseTopic;
      const startFrom = setupForm.start_from || "topic";
      const seedText = setupForm.seed_text.trim();
      const seed_components: Record<string, string> = {};
      if (startFrom === "scenario" && seedText) {
        seed_components.scenario = seedText;
      } else if (startFrom === "activity" && seedText) {
        seed_components.activity = seedText;
      } else if (startFrom === "experiment" && seedText) {
        seed_components.experiment = seedText;
      }
      const payload = await fetchJson<SessionResponse>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          topic: mergedTopic,
          grade_level: setupForm.grade_level,
          duration: setupForm.duration,
          classroom_mode: setupForm.classroom_mode,
          classroom_context: setupForm.classroom_context,
          hitl_enabled: setupForm.hitl_enabled,
          cascade_default: setupForm.cascade_default,
          multi_option: setupForm.multi_option,
          user_input: setupForm.request.trim(),
          start_from: startFrom,
          seed_components,
        }),
      });
      setSettings(setupForm);
      setSessionId(payload.session_id);
      localStorage.setItem("session_id", payload.session_id);
      setFeedbackText("");
      applySession(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action: "accept" | "reset" | "continue") => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/actions`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      if (action === "reset") {
        applySession(payload);
      } else {
        applySession(payload);
      }
      if (action === "accept") {
        setFeedbackMode(false);
        setFeedbackText("");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSendFeedback = async () => {
    if (!sessionId) return;
    const trimmed = feedbackText.trim();
    if (!trimmed) return;
    const localMessage: Message = {
      id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type: "user",
      message: trimmed,
      created_at: Date.now() / 1000,
    };
    setLocalMessages((prev) => [...prev, localMessage]);
    setFeedbackText("");
    setFeedbackMode(false);
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        action: "regenerate",
        feedback: trimmed,
      };
      const targetComponent = componentFromPath(selectedPath);
      if (targetComponent) {
        body.target_component = targetComponent;
      }
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/actions`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      applySession(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectCandidate = async (candidateId: string) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/actions`, {
        method: "POST",
        body: JSON.stringify({ action: "select_candidate", candidate_id: candidateId }),
      });
      applySession(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleToolTrigger = async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/tools`, {
        method: "POST",
        body: JSON.stringify({
          tool: "web_search",
          query: settings.topic || setupForm.topic || "",
        }),
      });
      applySession(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const performSaveEdit = async (
    path: string,
    content: string,
    cascade: boolean,
    continueAfter: boolean
  ) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/files`, {
        method: "PUT",
        body: JSON.stringify({
          path,
          content,
          cascade,
          lock: true,
        }),
      });
      setIsEditing(false);
      applySession(payload);
      if (continueAfter) {
        const nextPayload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/actions`, {
          method: "POST",
          body: JSON.stringify({ action: "continue" }),
        });
        applySession(nextPayload);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!sessionId || !selectedPath || !currentFile) return;
    if (!currentFile.editable) return;
    if (editValue === (currentFile.content ?? "")) {
      setIsEditing(false);
      return;
    }
    const component = componentFromPath(selectedPath);
    const targets = component ? cascadeTargets(component) : [];
    if (component && targets.length > 0) {
      setPendingSave({
        path: selectedPath,
        content: editValue,
        component,
        cascadeTargets: targets,
      });
      setShowSavePrompt(true);
      return;
    }
    await performSaveEdit(selectedPath, editValue, false, false);
  };

  const closeSavePrompt = () => {
    setShowSavePrompt(false);
    setPendingSave(null);
  };

  const handleSaveOnly = async () => {
    if (!pendingSave) return;
    const { path, content } = pendingSave;
    closeSavePrompt();
    await performSaveEdit(path, content, false, false);
  };

  const handleCascadeContinue = async () => {
    if (!pendingSave) return;
    const { path, content } = pendingSave;
    closeSavePrompt();
    await performSaveEdit(path, content, true, true);
  };

  const handleSelectFile = (path: string) => {
    if (isEditing && path !== selectedPath) {
      const proceed = window.confirm("当前内容未保存，确定切换吗？");
      if (!proceed) return;
      setIsEditing(false);
    }
    setSelectedPath(path);
    const selected = virtualFiles?.files.find((file) => file.path === path);
    setEditValue(selected?.content ?? "");
  };

  const awaitingUser = state?.await_user ?? false;
  const activeStage = task?.current_stage || deriveCurrentStage(state);
  const activeLabel = getStageLabel(activeStage);
  const activeProgress =
    buildTaskProgress(task, activeStage) ||
    buildProgressText(activeStage, state?.start_from || "topic");
  const stageSuffix = activeProgress ? `（${activeProgress}）` : "";
  const completed = isComplete(state);
  const pendingCandidates: Candidate[] = state?.pending_candidates || [];
  const selectedCandidateId = state?.selected_candidate_id || "";
  const showCandidates = awaitingUser && pendingCandidates.length > 0;

  let statusHeadline = "准备就绪";
  let statusDetail = "请在上方填写设置并开始生成。";
  if (loading) {
    statusHeadline = "智能体思考中";
    statusDetail = "正在处理下一步...";
  } else if (error) {
    statusHeadline = "错误";
    statusDetail = error;
  } else if (completed) {
    statusHeadline = "已完成";
    statusDetail = "在左侧打开 course_design.md 查看结果。";
  } else if (awaitingUser) {
    statusHeadline = "等待确认";
    statusDetail = activeStage ? `待确认：${activeLabel}${stageSuffix}` : "请确认或反馈修改。";
  } else if (sessionId) {
    statusHeadline = "进行中";
    statusDetail = activeStage ? `当前阶段：${activeLabel}${stageSuffix}` : "等待下一步生成。";
  }

  const showStatusBubble = Boolean(sessionId) && (loading || error || completed || awaitingUser || activeStage);
  const statusClass = error ? "error" : "status";

  const feedbackPlaceholder = feedbackMode || awaitingUser
    ? "请输入修改意见，回车发送（Shift+Enter 换行）"
    : "可输入修改意见，回车发送";

  const hasBaseInput = Boolean(
    setupForm.topic.trim() || setupForm.knowledge_point.trim() || setupForm.request.trim()
  );
  const seedRequired = setupForm.start_from !== "topic";
  const seedReady = !seedRequired || setupForm.seed_text.trim().length > 0;
  const canStart = !loading && (seedRequired ? seedReady : hasBaseInput);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          PBL 工作台
        </div>
        <div className="meta">
          {sessionId ? (
            <>
              <button className="button ghost tiny" onClick={handleNewSession}>
                重置任务
              </button>
              <span>会话 {sessionId.slice(0, 8)}</span>
            </>
          ) : (
            <span>未开始</span>
          )}
        </div>
      </header>

      <PanelGroup direction="horizontal" className="panel-group">
        <Panel defaultSize={20} minSize={14}>
          <div className="panel explorer">
            <div className="panel-header">
              <div className="panel-title">资源管理器</div>
              <div className="panel-subtitle">虚拟文件</div>
            </div>
            <div className="panel-body">
              {!virtualFiles && <div className="empty">暂无文件</div>}
              {virtualFiles && (
                <div className="file-section">
                  <div className="section-title">课程总览</div>
                  {courseDesignFile ? (
                    <button
                      className={`file-item ${selectedPath === courseDesignFile.path ? "active" : ""}`}
                      onClick={() => handleSelectFile(courseDesignFile.path)}
                    >
                      <span className="file-name">{displayFileName(courseDesignFile)}</span>
                      <span className="file-status">{STATUS_LABELS[courseDesignFile.status] || "信息"}</span>
                    </button>
                  ) : (
                    <div className="empty">暂无</div>
                  )}
                </div>
              )}

              {virtualFiles &&
                courseSections.map((section) => (
                  <div className="file-section" key={section.key}>
                    <div className="section-title">{section.title}</div>
                    {section.files.length === 0 ? (
                      <div className="empty">暂无</div>
                    ) : (
                      section.files.map((file) => (
                        <button
                          key={file.path}
                          className={`file-item ${selectedPath === file.path ? "active" : ""}`}
                          onClick={() => handleSelectFile(file.path)}
                        >
                          <span className="file-name">
                            {file.status === "pending" && <span className="status-dot" />}
                            {displayFileName(file)}
                          </span>
                          <span
                            className="file-status"
                            style={{ color: statusColor[file.status] || "var(--muted)" }}
                          >
                            {STATUS_LABELS[file.status] || "信息"}
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                ))}

            </div>
          </div>
        </Panel>
        <PanelResizeHandle className="resize-handle" />
        <Panel defaultSize={55} minSize={30}>
          <div className="panel editor">
            <div className="panel-header editor-header">
              <div className="editor-title">
                <div className="panel-title">预览</div>
                <div className="panel-subtitle">{selectedPath || "请选择文件"}</div>
              </div>
              <div className="panel-actions">
                {currentFile?.editable && (
                  <>
                    <button
                      className={`button ${isEditing ? "" : "primary"}`}
                      onClick={() => {
                        setEditValue(currentFile?.content ?? "");
                        setIsEditing(true);
                      }}
                      disabled={isEditing}
                    >
                      编辑
                    </button>
                    <button
                      className="button"
                      onClick={handleSaveEdit}
                      disabled={!isEditing || loading}
                    >
                      浏览
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="panel-body editor-body">
              {currentFile ? (
                isEditing ? (
                  <div className="markdown-edit">
                    <textarea
                      ref={editRef}
                      value={editValue}
                      onChange={(event) => setEditValue(event.target.value)}
                    />
                  </div>
                ) : (
                  <div className="markdown-view">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {displayMarkdown}
                    </ReactMarkdown>
                  </div>
                )
              ) : (
                <div className="empty">请选择文件以查看内容。</div>
              )}
            </div>
          </div>
        </Panel>
        <PanelResizeHandle className="resize-handle" />
        <Panel defaultSize={25} minSize={18}>
          <div className="panel chat">
            <div className="panel-header">
              <div className="panel-title">助手</div>
              <div className="panel-subtitle">{awaitingUser ? "等待确认" : "就绪"}</div>
            </div>
            <div className="panel-body chat-body">
              {!sessionId ? (
                <div className="settings">
                  <div className="settings-title">会话设置</div>
                  <div className="settings-grid">
                    <label>
                      年级
                      <select
                        value={setupForm.grade_level}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, grade_level: event.target.value }))
                        }
                      >
                        <option value="小学">小学</option>
                        <option value="初中">初中</option>
                        <option value="高中">高中</option>
                      </select>
                    </label>
                    <label>
                      时长（分钟）
                      <input
                        type="number"
                        min={10}
                        value={setupForm.duration}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, duration: Number(event.target.value) }))
                        }
                      />
                    </label>
                    <label>
                      课堂模式
                      <select
                        value={setupForm.classroom_mode}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, classroom_mode: event.target.value }))
                        }
                      >
                        <option value="normal">常规</option>
                        <option value="no_device">无设备</option>
                        <option value="computer_lab">机房</option>
                      </select>
                    </label>
                    <label>
                      Start From
                      <select
                        value={setupForm.start_from}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, start_from: event.target.value }))
                        }
                      >
                        <option value="topic">topic</option>
                        <option value="scenario">scenario</option>
                        <option value="activity">activity</option>
                        <option value="experiment">experiment</option>
                      </select>
                    </label>
                    {setupForm.start_from !== "topic" && (
                      <label className="full-span">
                        Seed Content
                        <textarea
                          value={setupForm.seed_text}
                          onChange={(event) =>
                            setSetupForm((prev) => ({ ...prev, seed_text: event.target.value }))
                          }
                          placeholder="Paste existing content for the selected stage."
                        />
                      </label>
                    )}
                    <label>
                      主题
                      <input
                        value={setupForm.topic}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, topic: event.target.value }))
                        }
                        placeholder="例如：图像识别"
                      />
                    </label>
                    <label>
                      知识点
                      <input
                        value={setupForm.knowledge_point}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, knowledge_point: event.target.value }))
                        }
                        placeholder="例如：卷积神经网络"
                      />
                    </label>
                    <label>
                      课堂背景
                      <input
                        value={setupForm.classroom_context}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, classroom_context: event.target.value }))
                        }
                        placeholder="可选"
                      />
                    </label>
                    <label className="full-span">
                      需求描述
                      <textarea
                        value={setupForm.request}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, request: event.target.value }))
                        }
                        placeholder="一句话描述期望的课程设计"
                      />
                    </label>
                  </div>
                  <div className="toggle-row">
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={setupForm.hitl_enabled}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, hitl_enabled: event.target.checked }))
                        }
                      />
                      启用确认（HITL）
                    </label>
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={setupForm.cascade_default}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, cascade_default: event.target.checked }))
                        }
                      />
                      启用级联
                    </label>
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={setupForm.multi_option}
                        onChange={(event) =>
                          setSetupForm((prev) => ({ ...prev, multi_option: event.target.checked }))
                        }
                      />
                      多方案
                    </label>
                  </div>
                  <div className="settings-actions">
                    <button
                      className="button primary"
                      onClick={handleStart}
                      disabled={!canStart}
                    >
                      开始
                    </button>
                  </div>
                </div>
              ) : (
                <div className="settings compact">
                  <div className="settings-line">
                    会话设置：年级 {settings.grade_level || "未指定"}｜时长 {settings.duration} 分钟｜模式{" "}
                    {MODE_LABELS[settings.classroom_mode] || settings.classroom_mode}｜主题{" "}
                    {settings.topic || "未指定"}｜知识点 {settings.knowledge_point || "未指定"}｜确认{" "}
                    {settings.hitl_enabled ? "开启" : "关闭"}｜级联{" "}
                    {settings.cascade_default ? "开启" : "关闭"}｜多方案{" "}
                    {settings.multi_option ? "开启" : "关闭"}
                  <div>start_from: {settings.start_from || "topic"}</div>
                  <div>seed: {settings.seed_text ? "(provided)" : "(empty)"}</div>
                  </div>
                  <button
                    className="button ghost tiny"
                    onClick={() => setShowSettingsDetails((prev) => !prev)}
                  >
                    {showSettingsDetails ? "收起" : "展开"}
                  </button>
                </div>
              )}
              {sessionId && showSettingsDetails && (
                <div className="settings-detail">
                  <div>年级：{settings.grade_level || "未指定"}</div>
                  <div>时长：{settings.duration} 分钟</div>
                  <div>模式：{MODE_LABELS[settings.classroom_mode] || settings.classroom_mode}</div>
                  <div>主题：{settings.topic || "未指定"}</div>
                  <div>知识点：{settings.knowledge_point || "未指定"}</div>
                  <div>课堂背景：{settings.classroom_context || "未指定"}</div>
                  <div>需求描述：{settings.request || "未指定"}</div>
                  <div>确认：{settings.hitl_enabled ? "开启" : "关闭"}</div>
                  <div>级联：{settings.cascade_default ? "开启" : "关闭"}</div>
                  <div>多方案：{settings.multi_option ? "开启" : "关闭"}</div>
                </div>
              )}

              {sessionId && (
                <div className="chat-messages">
                  {combinedMessages.length === 0 && !showCandidates && !showStatusBubble ? (
                    <div className="empty">暂无消息</div>
                  ) : (
                    combinedMessages.map((event) => (
                      <div key={event.id} className={`chat-event ${event.type}`}>
                        <div className="chat-event-text">{event.message}</div>
                      </div>
                    ))
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}

              {showCandidates && (
                <div className="candidate-panel">
                  <div className="candidate-title">可选方案</div>
                  {pendingCandidates.map((candidate) => (
                    <button
                      key={candidate.id}
                      className={`candidate-item ${
                        candidate.id === selectedCandidateId ? "active" : ""
                      }`}
                      onClick={() => handleSelectCandidate(candidate.id)}
                      disabled={loading}
                    >
                      <span className="candidate-id">{candidate.id}</span>
                      <span className="candidate-text">
                        {candidate.title || candidate.driving_question || "（未命名方案）"}
                      </span>
                    </button>
                  ))}
                  <div className="candidate-tip">请选择一个方案，或在下方输入修改意见。</div>
                </div>
              )}

                            {showStatusBubble && (
                <div className={`chat-event ${statusClass}`}>
                  {loading ? (
                    <div className="thinking">
                      ??????
                      <span className="dots">
                        <span>.</span>
                        <span>.</span>
                        <span>.</span>
                      </span>
                    </div>
                  ) : (
                    <div className="status-text">{statusHeadline}</div>
                  )}
                  <div className="status-detail">{statusDetail}</div>
                  {awaitingUser && (
                    <div className="chat-event-actions">
                      <button className="button primary" onClick={() => handleAction("accept")} disabled={loading}>
                        ??
                      </button>
                      <button
                        className="button"
                        onClick={() => {
                          setFeedbackMode(true);
                          inputRef.current?.focus();
                        }}
                        disabled={loading}
                      >
                        ??
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="chat-input">
              {sessionId && (
                <div className="tool-actions">
                  <button
                    className="button ghost tiny"
                    onClick={handleToolTrigger}
                    disabled={loading}
                  >
                    联网查找资料
                  </button>
                </div>
              )}
              <textarea
                ref={inputRef}
                rows={4}
                placeholder={sessionId ? feedbackPlaceholder : "会话未开始，先完成上方设置"}
                value={feedbackText}
                onChange={(event) => setFeedbackText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    if (!loading && sessionId) {
                      handleSendFeedback();
                    }
                  }
                }}
                disabled={!sessionId}
              />
              {error && !loading && <div className="error">{error}</div>}
            </div>
          </div>
        </Panel>
      </PanelGroup>
      {showSavePrompt && pendingSave && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-title">Save changes?</div>
            <div className="modal-body">
              <div>Component: {getStageLabel(pendingSave.component)}</div>
              <div>
                Downstream reset: {pendingSave.cascadeTargets.map(getStageLabel).join(", ")}
              </div>
            </div>
            <div className="modal-actions">
              <button className="button" onClick={closeSavePrompt} disabled={loading}>
                Cancel
              </button>
              <button className="button" onClick={handleSaveOnly} disabled={loading}>
                Save Only
              </button>
              <button className="button primary" onClick={handleCascadeContinue} disabled={loading}>
                Cascade + Continue
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
