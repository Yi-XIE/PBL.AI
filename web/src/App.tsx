import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentState, SessionResponse, VirtualFile, VirtualFilesPayload } from "./types";

type Settings = {
  topic: string;
  knowledge_point: string;
  grade_level: string;
  duration: number;
  classroom_mode: string;
  classroom_context: string;
  hitl_enabled: boolean;
  cascade_default: boolean;
  request: string;
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
  request: "",
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

const COMPONENT_LABELS: Record<string, string> = {
  scenario: "情境",
  driving_question: "驱动问题",
  question_chain: "问题链",
  activity: "活动",
  experiment: "实验",
};

const FILE_LABELS: Record<string, string> = {
  "course/course_design.md": "课程总览",
  "course/scenario.md": "情景",
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

function isComplete(state: AgentState | null) {
  if (!state) return false;
  const progress = state.design_progress || {};
  const startFrom = state.start_from || "topic";
  const required =
    startFrom === "activity"
      ? ["activity", "experiment"]
      : startFrom === "experiment"
      ? ["experiment"]
      : ["scenario", "driving_question", "question_chain", "activity", "experiment"];
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
  const [displayMarkdown, setDisplayMarkdown] = useState("");
  const [feedbackMode, setFeedbackMode] = useState(false);

  const lastPendingRef = useRef<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const editRef = useRef<HTMLTextAreaElement | null>(null);
  const streamedRef = useRef<Set<string>>(new Set());

  const { courseDesignFile, courseSections, debugFiles } = useMemo(() => {
    const files = virtualFiles?.files || [];
    const courseFiles = files.filter(
      (file) =>
        file.path.startsWith("course/") &&
        file.path !== "course/course_design.json"
    );
    const debug = files.filter((file) => file.path.startsWith("debug/"));
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
      debugFiles: debug.sort((a, b) => a.path.localeCompare(b.path)),
    };
  }, [virtualFiles]);

  const currentFile = useMemo(() => {
    return virtualFiles?.files.find((file) => file.path === selectedPath) || null;
  }, [selectedPath, virtualFiles]);

  const renderedMarkdown = buildMarkdown(currentFile);

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

  const applySession = (payload: SessionResponse) => {
    setState(payload.state);
    setVirtualFiles(payload.virtual_files);
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

  const loadSession = async (id: string) => {
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
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    if (sessionId) {
      loadSession(sessionId);
    }
  }, []);

  const handleStart = async () => {
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
          user_input: setupForm.request.trim(),
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

  const handleAction = async (action: "accept" | "reset") => {
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
    if (!feedbackText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        action: "regenerate",
        feedback: feedbackText.trim(),
      };
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/actions`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setFeedbackText("");
      setFeedbackMode(false);
      applySession(payload);
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
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/files`, {
        method: "PUT",
        body: JSON.stringify({
          path: selectedPath,
          content: editValue,
          cascade: settings.cascade_default,
          lock: true,
        }),
      });
      setIsEditing(false);
      applySession(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/sessions/${sessionId}/export`);
      if (!response.ok) {
        throw new Error(response.statusText);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "course_design.json";
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
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
  const pendingComponent = state?.pending_component || state?.current_component || "";
  const pendingLabel = COMPONENT_LABELS[pendingComponent] || pendingComponent || "暂无";
  const completed = isComplete(state);

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
    statusDetail = pendingComponent ? `待确认：${pendingLabel}` : "请确认或反馈修改。";
  } else if (sessionId) {
    statusHeadline = "进行中";
    statusDetail = pendingComponent ? `当前阶段：${pendingLabel}` : "等待下一步生成。";
  }

  const feedbackPlaceholder = feedbackMode || awaitingUser
    ? "请输入修改意见，回车发送（Shift+Enter 换行）"
    : "可输入修改意见，回车发送";

  const canStart =
    !loading &&
    (setupForm.topic.trim() || setupForm.knowledge_point.trim() || setupForm.request.trim());

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          PBL 工作台
        </div>
        <div className="meta">
          {sessionId ? (
            <span>会话 {sessionId.slice(0, 8)}</span>
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

              {virtualFiles && debugFiles.length > 0 && (
                <div className="file-section">
                  <div className="section-title">调试</div>
                  {debugFiles.map((file) => (
                    <button
                      key={file.path}
                      className={`file-item ${selectedPath === file.path ? "active" : ""}`}
                      onClick={() => handleSelectFile(file.path)}
                    >
                      <span className="file-name">{file.path.split("/").pop()}</span>
                      <span className="file-status">{STATUS_LABELS[file.status] || "信息"}</span>
                    </button>
                  ))}
                </div>
              )}
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
                    {settings.cascade_default ? "开启" : "关闭"}
                  </div>
                  <div className="settings-actions">
                    <button className="button" onClick={handleExport} disabled={!sessionId || loading}>
                      下载 JSON
                    </button>
                    <button
                      className="button ghost"
                      onClick={() => handleAction("reset")}
                      disabled={!sessionId || loading}
                    >
                      重置
                    </button>
                  </div>
                </div>
              )}

              <div className="status-card">
                <div className="status-title">状态</div>
                {loading ? (
                  <div className="thinking">
                    智能体思考中
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
                  <div className="status-actions">
                    <button className="button primary" onClick={() => handleAction("accept")} disabled={loading}>
                      接受
                    </button>
                    <button
                      className="button"
                      onClick={() => {
                        setFeedbackMode(true);
                        inputRef.current?.focus();
                      }}
                      disabled={loading}
                    >
                      拒绝
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="chat-input">
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
    </div>
  );
}
