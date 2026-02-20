export type VirtualFile = {
  path: string;
  language: string;
  editable: boolean;
  status: string;
  content: string;
};

export type VirtualFilesPayload = {
  files: VirtualFile[];
  selected_default?: string;
};

export type AgentState = {
  await_user?: boolean;
  pending_component?: string | null;
  pending_preview?: Record<string, unknown>;
  pending_candidates?: Candidate[];
  selected_candidate_id?: string | null;
  hitl_enabled?: boolean;
  cascade_default?: boolean;
  multi_option?: boolean;
  start_from?: string;
  design_progress?: Record<string, boolean>;
  component_validity?: Record<string, string>;
  locked_components?: string[];
  action_sequence?: string[];
  current_component?: string;
};

export type Candidate = {
  id: string;
  title?: string;
  driving_question?: string;
  question_chain?: string[];
  rationale?: string;
};

export type Task = {
  task_id: string;
  session_id: string;
  topic: string;
  stages: string[];
  current_stage: string;
  completed_stages: string[];
  status: "active" | "completed";
  created_at: number;
};

export type Message = {
  id: string;
  type: "status" | "explanation" | "action" | "tool_status";
  message: string;
  stage?: string | null;
  created_at: number;
};

export type SessionResponse = {
  session_id: string;
  state: AgentState;
  virtual_files: VirtualFilesPayload;
  task?: Task | null;
  messages?: Message[];
  error?: string | null;
};
