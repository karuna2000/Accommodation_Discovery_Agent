export interface ExecuteEvent {
  step_index: number;
  results?: Record<string, unknown>[];
  result?: string;
  error?: string;
  step_vars?: Record<string, string>;
}

export interface AgentEvent {
  plan?: { plan: string };
  execute?: ExecuteEvent;
  evaluate?: { decision: string };
  synthesize?: { synthesized_answer: string };
  [key: string]: unknown;
}

export interface DonePayload {
  type: "done";
  search_id: string;
  answer: string;
  error: string | null;
}

export interface EventPayload {
  type: "event";
  data: AgentEvent;
}

export type ServerMessage = EventPayload | DonePayload;

export interface StepInfo {
  id: string;
  type: "plan" | "execute" | "evaluate" | "synthesize";
  label: string;
  summary: string;
  detail: string;
  status: "running" | "done" | "error";
  results?: Record<string, unknown>[];
  toolName?: string;
  startedAt: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}
