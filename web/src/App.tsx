import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import ReactMarkdown from "react-markdown";
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
    return "_No content yet._";
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

  const lastPendingRef = useRef<string | null>(null);

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
      const payload = await fetchJson<SessionResponse>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          ...settings,
          user_input: inputText.trim(),
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

  const handleAction = async (action: "accept" | "continue" | "regenerate" | "reset") => {
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
    setSelectedPath(path);
  };

  const awaitingUser = state?.await_user ?? false;
  const pendingComponent = state?.pending_component || state?.current_component || "";
  const completed = isComplete(state);
  const readyToContinue = !!sessionId && !awaitingUser && !completed;

  let statusHeadline = "准备就绪";
  let statusDetail = "请输入需求以开始。";
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
    statusDetail = pendingComponent ? `下一步：${pendingComponent}` : "可以继续生成。";
  }

  const inputPlaceholder = sessionId
    ? "填写反馈后点击 Regenerate。"
    : "描述你想生成的课程...";

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
            <span>No active session</span>
          )}
        </div>
      </header>

      <PanelGroup direction="horizontal" className="panel-group">
        <Panel defaultSize={20} minSize={14}>
          <div className="panel explorer">
            <div className="panel-header">
              <div className="panel-title">Explorer</div>
              <div className="panel-subtitle">Virtual files</div>
            </div>
            <div className="panel-body">
              {Object.keys(groupedFiles).length === 0 && (
                <div className="empty">No files yet</div>
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
              <div className="panel-title">Viewer</div>
              <div className="panel-subtitle">
                {selectedPath || "Select a file"}
              </div>
            </div>
            <div className="panel-body editor-body">
              {currentFile ? (
                <div className="markdown-view">
                  <ReactMarkdown>{renderedMarkdown}</ReactMarkdown>
                </div>
              ) : (
                <div className="empty">Select a file to view content.</div>
              )}
            </div>
          </div>
        </Panel>
        <PanelResizeHandle className="resize-handle" />
        <Panel defaultSize={25} minSize={18}>
          <div className="panel chat">
            <div className="panel-header">
              <div className="panel-title">Agent</div>
              <div className="panel-subtitle">{awaitingUser ? "Awaiting approval" : "Ready"}</div>
            </div>
            <div className="panel-body chat-body">
              <div className="settings">
                <div className="settings-title">Session Settings</div>
                <div className="settings-grid">
                  <label>
                    Topic
                    <input
                      value={settings.topic}
                      onChange={(event) =>
                        setSettings((prev) => ({ ...prev, topic: event.target.value }))
                      }
                      disabled={!!sessionId}
                      placeholder="e.g. Image recognition"
                    />
                  </label>
                  <label>
                    Grade
                    <input
                      value={settings.grade_level}
                      onChange={(event) =>
                        setSettings((prev) => ({ ...prev, grade_level: event.target.value }))
                      }
                      disabled={!!sessionId}
                      placeholder="e.g. middle school"
                    />
                  </label>
                  <label>
                    Duration
                    <input
                      type="number"
                      min={10}
                      value={settings.duration}
                      onChange={(event) =>
                        setSettings((prev) => ({
                          ...prev,
                          duration: Number(event.target.value),
                        }))
                      }
                      disabled={!!sessionId}
                    />
                  </label>
                  <label>
                    Classroom Mode
                    <select
                      value={settings.classroom_mode}
                      onChange={(event) =>
                        setSettings((prev) => ({
                          ...prev,
                          classroom_mode: event.target.value,
                        }))
                      }
                      disabled={!!sessionId}
                    >
                      <option value="normal">normal</option>
                      <option value="no_device">no_device</option>
                      <option value="computer_lab">computer_lab</option>
                    </select>
                  </label>
                  <label>
                    Classroom Context
                    <input
                      value={settings.classroom_context}
                      onChange={(event) =>
                        setSettings((prev) => ({
                          ...prev,
                          classroom_context: event.target.value,
                        }))
                      }
                      disabled={!!sessionId}
                      placeholder="Optional notes"
                    />
                  </label>
                </div>
                <div className="toggle-row">
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={settings.hitl_enabled}
                      onChange={(event) =>
                        setSettings((prev) => ({ ...prev, hitl_enabled: event.target.checked }))
                      }
                      disabled={!!sessionId}
                    />
                    HITL
                  </label>
                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={settings.cascade_default}
                      onChange={(event) =>
                        setSettings((prev) => ({
                          ...prev,
                          cascade_default: event.target.checked,
                        }))
                      }
                      disabled={!!sessionId}
                    />
                    Cascade
                  </label>
                </div>
                <div className="settings-actions">
                  <button
                    className="button primary"
                    onClick={handleStart}
                    disabled={loading || !!sessionId}
                  >
                    Start
                  </button>
                  <button
                    className="button"
                    onClick={handleExport}
                    disabled={!sessionId || loading}
                  >
                    Download
                  </button>
                  <button
                    className="button ghost"
                    onClick={() => handleAction("reset")}
                    disabled={!sessionId || loading}
                  >
                    Reset
                  </button>
                </div>
              </div>

              <div className="status-card">
                <div className="status-title">Agent Status</div>
                {loading ? (
                  <div className="thinking">
                    Agent思考中
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
              </div>
            </div>

            <div className="chat-input">
              <textarea
                rows={3}
                placeholder={inputPlaceholder}
                value={inputText}
                onChange={(event) => setInputText(event.target.value)}
              />
              <div className="chat-actions">
                <select
                  value={regenTarget}
                  onChange={(event) => setRegenTarget(event.target.value)}
                >
                  <option value="pending">pending</option>
                  {COMPONENTS.map((component) => (
                    <option key={component} value={component}>
                      {component}
                    </option>
                  ))}
                </select>
                <button
                  className="button primary"
                  onClick={() => handleAction("accept")}
                  disabled={!awaitingUser || loading}
                >
                  Accept
                </button>
                <button
                  className="button"
                  onClick={() => handleAction("regenerate")}
                  disabled={!awaitingUser || loading}
                >
                  Regenerate
                </button>
                <button
                  className="button"
                  onClick={() => handleAction("continue")}
                  disabled={!readyToContinue || loading}
                >
                  Continue
                </button>
              </div>
              {error && !loading && <div className="error">{error}</div>}
            </div>
          </div>
        </Panel>
      </PanelGroup>
    </div>
  );
}
