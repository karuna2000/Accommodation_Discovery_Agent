import { useCallback, useRef, useState } from "react";
import type { ChatMessage, ServerMessage } from "../types";

interface UseSearchReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  searchId: string | null;
  error: string | null;
  submitQuery: (query: string) => Promise<void>;
  cancelSearch: () => Promise<void>;
  clearMessages: () => void;
}

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function makeSystemMessage(
  label: string,
  content: string,
): ChatMessage {
  return {
    id: genId(),
    role: "system",
    content: `**${label}**\n${content}`,
    timestamp: Date.now(),
  };
}

export function useSearch(): UseSearchReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const submitQuery = useCallback(async (query: string) => {
    const abort = new AbortController();
    abortRef.current = abort;
    setIsStreaming(true);
    setError(null);

    const userMsg: ChatMessage = {
      id: genId(),
      role: "user",
      content: query,
      timestamp: Date.now(),
    };

    const thinkingMsg: ChatMessage = {
      id: genId(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg, thinkingMsg]);

    const idempotencyKey = crypto.randomUUID();

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({ query, max_iterations: 10 }),
        signal: abort.signal,
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({ error: "Request failed" }));
        throw new Error(errBody.error || `HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let parsed: ServerMessage;
          try {
            parsed = JSON.parse(raw);
          } catch {
            continue;
          }

          if (parsed.type === "done") {
            setSearchId(parsed.search_id);
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: parsed.answer || "No results found.",
                };
              }
              return updated;
            });
            if (parsed.error) setError(parsed.error);
          } else if (parsed.type === "event") {
            const event = parsed.data;
            const plan = event.plan;
            const execute = event.execute;
            const evaluate = event.evaluate;
            const synthesize = event.synthesize;

            if (plan) {
              setMessages((prev) => [
                ...prev,
                makeSystemMessage("Plan", plan.plan),
              ]);
            }
            if (execute) {
              setMessages((prev) => [
                ...prev,
                makeSystemMessage("Step " + (execute.step_index ?? ""), execute.result || "Running tool..."),
              ]);
            }
            if (evaluate) {
              setMessages((prev) => [
                ...prev,
                makeSystemMessage("Evaluate", `Decision: ${evaluate.decision}`),
              ]);
            }
            if (synthesize) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: synthesize.synthesized_answer || last.content,
                  };
                }
                return updated;
              });
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setMessages((prev) => [
          ...prev,
          makeSystemMessage("Cancelled", "Search was cancelled."),
        ]);
      } else {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
        setMessages((prev) => [
          ...prev,
          makeSystemMessage("Error", msg),
        ]);
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }, []);

  const cancelSearch = useCallback(async () => {
    if (searchId) {
      try {
        await fetch(`/api/search/${searchId}/cancel`, { method: "POST" });
      } catch {
        // best-effort
      }
    }
    abortRef.current?.abort();
  }, [searchId]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSearchId(null);
    setError(null);
  }, []);

  return {
    messages,
    isStreaming,
    searchId,
    error,
    submitQuery,
    cancelSearch,
    clearMessages,
  };
}
