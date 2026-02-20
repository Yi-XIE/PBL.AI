import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentState, SessionResponse, VirtualFile, VirtualFilesPayload } from "./types";

type Settings = {
  topic: string;
  grade_level: string;
  duration: number;
  classroom_mode: string;
  classroom_context: string;
  hitl_enabled: boolean;
  cascade_default: boolean;
};

const DEFAULT_SETTINGS: Settings = {
  topic: "",
  grade_level: "",
  duration: 80,
  classroom_mode: "normal",
  classroom_context: "",
  hitl_enabled: true,
  cascade_default: true,
};

const COMPONENTS = ["scenario", "driving_question", "question_chain", "activity", "experiment"];

const statusColor: Record<string, string> = {
  pending: "var(--accent)",
  locked: "var(--good)",
  invalid: "var(--danger)",
  valid: "var(--info)",
  empty: "var(--muted)",
  info: "var(--muted)",
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

function parseSetupInput(
  text: string,
  defaults: Settings
): { settings: Settings; userInput: string } {
  const settings = { ...defaults };
  const raw = text.trim();
  if (!raw) {
    return { settings, userInput: "" };
  }
  const normalized = raw.toLowerCase();

  if (normalized.match(/小学|primary/)) settings.grade_level = "小学";
  if (normalized.match(/初中|middle/)) settings.grade_level = "初中";
  if (normalized.match(/高中|high/)) settings.grade_level = "高中";

  const durationMatch = raw.match(/(\d+)\s*(分钟|min|mins)/);
  if (durationMatch) settings.duration = Number(durationMatch[1]);

  if (normalized.match(/no_device|无设备|无电子/)) settings.classroom_mode = "no_device";
  if (normalized.match(/computer_lab|机房|计算机教室/)) settings.classroom_mode = "computer_lab";
  if (normalized.match(/normal|常规|普通/)) settings.classroom_mode = "normal";

  if (normalized.match(/hitl\s*=\s*off|不需要确认|自动接受/)) settings.hitl_enabled = false;
  if (normalized.match(/hitl\s*=\s*on|需要确认|人工确认/)) settings.hitl_enabled = true;

  if (normalized.match(/cascade\s*=\s*off|不级联|关闭级联/)) settings.cascade_default = false;
  if (normalized.match(/cascade\s*=\s*on|开启级联|级联/)) settings.cascade_default = true;

  const topicMatch = raw.match(/(?:topic|主题|话题)\s*[:=：]\s*([^\n;]+)/i);
  if (topicMatch) settings.topic = topicMatch[1].trim();

  const contextMatch = raw.match(/(?:课堂|情境|context)\s*[:=：]\s*([^\n;]+)/i);
  if (contextMatch) settings.classroom_context = contextMatch[1].trim();

  const requestMatch = raw.match(/(?:需求|描述|要求|request)\s*[:=：]\s*([\s\S]+)/i);
  let userInput = requestMatch ? requestMatch[1].trim() : raw;
  if (topicMatch && userInput === raw) {
    userInput = raw.replace(topicMatch[0], "").trim();
  }
  if (!userInput && settings.topic) {
    userInput = "";
  }
  return { settings, userInput };
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

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(() => {
    return localStorage.getItem("session_id");
  });
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [state, setState] = useState<AgentState | null>(null);
  const [virtualFiles, setVirtualFiles] = useState<VirtualFilesPayload | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [regenTarget, setRegenTarget] = useState("pending");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState("");

  const lastPendingRef = useRef<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const editRef = useRef<HTMLTextAreaElement | null>(null);

  const groupedFiles = useMemo(() => {
    const groups: Record<string, VirtualFile[]> = {};
    (virtualFiles?.files || []).forEach((file) => {
      const root = file.path.split("/")[0] || "root";
      if (!groups[root]) {
        groups[root] = [];
      }
      groups[root].push(file);
    });
    Object.values(groups).forEach((group) => group.sort((a, b) => a.path.localeCompare(b.path)));
    return groups;
  }, [virtualFiles]);

  const currentFile = useMemo(() => {
    return virtualFiles?.files.find((file) => file.path === selectedPath) || null;
  }, [selectedPath, virtualFiles]);

  const renderedMarkdown = buildMarkdown(currentFile);

  useEffect(() => {
    if (!inputRef.current) return;
    inputRef.current.style.height = "auto";
    inputRef.current.style.height = `${inputRef.current.scrollHeight}px`;
  }, [inputText]);

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
      const parsed = parseSetupInput(inputText, settings);
      setSettings(parsed.settings);
      const payload = await fetchJson<SessionResponse>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          ...parsed.settings,
          user_input: parsed.userInput,
        }),
      });
      setSessionId(payload.session_id);
      localStorage.setItem("session_id", payload.session_id);
      setInputText("");
      applySession(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action: "accept" | "regenerate" | "reset") => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { action };
      if (action === "regenerate") {
        if (!inputText.trim()) {
          setLoading(false);
          return;
        }
        body.feedback = inputText.trim();
        if (regenTarget !== "pending") {
          body.target_component = regenTarget;
        }
        setInputText("");
      }
      const payload = await fetchJson<SessionResponse>(`/api/sessions/${sessionId}/actions`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (action === "reset") {
        applySession(payload);
      } else {
        applySession(payload);
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

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditValue(currentFile?.content ?? "");
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
  const completed = isComplete(state);

  let statusHeadline = "准备就绪";
  let statusDetail = "请在下方一次性回答问题并描述需求。";
  if (loading) {
    statusHeadline = "Agent 思考中";
    statusDetail = "正在处理下一步...";
  } else if (error) {
    statusHeadline = "错误";
    statusDetail = error;
  } else if (completed) {
    statusHeadline = "已完成";
    statusDetail = "在左侧打开 course_design.md 查看结果。";
  } else if (awaitingUser) {
    statusHeadline = "等待确认";
    statusDetail = pendingComponent ? `待确认：${pendingComponent}` : "请确认或反馈修改。";
  } else if (sessionId) {
    statusHeadline = "进行中";
    statusDetail = pendingComponent ? `当前阶段：${pendingComponent}` : "可以继续生成。";
  }

  const inputPlaceholder = sessionId
    ? "填写反馈后点击“重新生成”。"
    : "按“题目/年级/时长/模式/确认方式”一次性回答，并附上需求描述。";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          PBL Studio
        </div>
        <div className="meta">
          {sessionId ? (
            <span>Session {sessionId.slice(0, 8)}</span>
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
              {Object.keys(groupedFiles).length === 0 && (
                <div className="empty">暂无文件</div>
              )}
              {Object.entries(groupedFiles).map(([group, files]) => (
                <div className="file-group" key={group}>
                  <div className="group-title">{group}</div>
                  {files.map((file) => (
                    <button
                      key={file.path}
                      className={`file-item ${selectedPath === file.path ? "active" : ""}`}
                      onClick={() => handleSelectFile(file.path)}
                    >
                      <span className="file-name">{file.path.split("/").pop()}</span>
                      <span
                        className="file-status"
                        style={{ color: statusColor[file.status] || "var(--muted)" }}
                      >
                        {file.status}
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </Panel>
        <PanelResizeHandle className="resize-handle" />
        <Panel defaultSize={55} minSize={30}>
          <div className="panel editor">
            <div className="panel-header">
              <div className="panel-title">预览</div>
              <div className="panel-subtitle">
                {selectedPath || "请选择文件"}
              </div>
              <div className="panel-actions">
                {currentFile?.editable && !isEditing && (
                  <button
                    className="button"
                    onClick={() => {
                      setEditValue(currentFile?.content ?? "");
                      setIsEditing(true);
                    }}
                  >
                    编辑
                  </button>
                )}
                {isEditing && (
                  <>
                    <button className="button primary" onClick={handleSaveEdit} disabled={loading}>
                      保存
                    </button>
                    <button className="button" onClick={handleCancelEdit} disabled={loading}>
                      取消
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
                      {renderedMarkdown}
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
                  <div className="settings-title">Session 问答</div>
                  <div className="question-list">
                    <div className="question-item">
                      1. 年级：小学 / 初中 / 高中
                    </div>
                    <div className="question-item">
                      2. 时长：40分钟 / 80分钟 / 90分钟（可自定义）
                    </div>
                    <div className="question-item">
                      3. 课堂模式：normal / no_device / computer_lab
                    </div>
                    <div className="question-item">
                      4. 是否需要确认：HITL=on / HITL=off
                    </div>
                    <div className="question-item">
                      5. 是否级联：cascade=on / cascade=off
                    </div>
                    <div className="question-tip">
                      示例：主题=图像识别；初中；80分钟；normal；HITL=on；cascade=on；需求：设计一节PBL课程
                    </div>
                  </div>
                  <div className="settings-actions">
                    <button
                      className="button primary"
                      onClick={handleStart}
                      disabled={loading || !inputText.trim()}
                    >
                      开始
                    </button>
                  </div>
                </div>
              ) : (
                <div className="settings compact">
                  <div className="settings-title">Session 设置</div>
                  <div className="settings-summary">
                    <div>年级：{settings.grade_level || "未指定"}</div>
                    <div>时长：{settings.duration} 分钟</div>
                    <div>模式：{settings.classroom_mode}</div>
                    <div>确认：{settings.hitl_enabled ? "开启" : "关闭"}</div>
                    <div>级联：{settings.cascade_default ? "开启" : "关闭"}</div>
                  </div>
                  <div className="settings-actions">
                    <button
                      className="button"
                      onClick={handleExport}
                      disabled={!sessionId || loading}
                    >
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
                    Agent 思考中
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
                    <button
                      className="button primary"
                      onClick={() => handleAction("accept")}
                      disabled={loading}
                    >
                      接受
                    </button>
                    <button
                      className="button"
                      onClick={() => handleAction("regenerate")}
                      disabled={loading}
                    >
                      重新生成
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="chat-input">
              {sessionId && (
                <div className="pending-bar">
                  <span>当前阶段：{pendingComponent || "无"}</span>
                  <select
                    value={regenTarget}
                    onChange={(event) => setRegenTarget(event.target.value)}
                  >
                    <option value="pending">当前</option>
                    {COMPONENTS.map((component) => (
                      <option key={component} value={component}>
                        {component}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <textarea
                ref={inputRef}
                rows={4}
                placeholder={inputPlaceholder}
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
              />
              {error && !loading && <div className="error">{error}</div>}
            </div>
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
