export interface AgentEvent {
  plan?: { plan: string };
  execute?: { step_index: number; result: string };
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

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "plan" | "execute" | "evaluate";
  content: string;
  timestamp: number;
}
