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
  hitl_enabled?: boolean;
  cascade_default?: boolean;
  start_from?: string;
  design_progress?: Record<string, boolean>;
  component_validity?: Record<string, string>;
  locked_components?: string[];
  action_sequence?: string[];
  current_component?: string;
};

export type SessionResponse = {
  session_id: string;
  state: AgentState;
  virtual_files: VirtualFilesPayload;
  error?: string | null;
};
