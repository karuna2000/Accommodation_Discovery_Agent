import { useCallback, useRef, useState } from "react";
import type { ChatMessage, ServerMessage, StepInfo } from "../types";

interface UseSearchReturn {
  messages: ChatMessage[];
  steps: StepInfo[];
  isStreaming: boolean;
  searchId: string | null;
  error: string | null;
  submitQuery: (query: string) => Promise<void>;
  cancelSearch: () => Promise<void>;
  clearMessages: () => void;
  searchStartedAt: number | null;
  searchCompletedAt: number | null;
}

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function parsePlanLines(planText: string): string[] {
  return planText
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => /^\d+\./.test(l));
}

function extractToolName(line: string): string {
  const m = line.match(/\.\s*(\w+)/);
  return m ? m[1] : "unknown";
}

function formatStepLabel(
  stepType: StepInfo["type"],
  toolName?: string,
  detail?: string,
): string {
  if (stepType === "plan") return "Planning";
  if (stepType === "evaluate") return `Evaluating ${detail ? `→ ${detail}` : ""}`;
  if (stepType === "synthesize") return "Generating answer";
  if (stepType === "execute" && toolName) {
    switch (toolName) {
      case "search_web":
        return "Searching web";
      case "scrape_url":
        return "Scraping page";
      case "extract_property":
        return "Extracting data";
      case "search_es":
        return "Searching cache";
      default:
        return `Running ${toolName}`;
    }
  }
  return "Processing";
}

function formatExecuteSummary(
  toolName: string,
  eventData: Record<string, unknown>,
): string {
  const err = eventData.error as string | undefined;
  if (err) return `Error: ${err}`;
  const results = eventData.results as Record<string, unknown>[] | undefined;
  if (!results || results.length === 0) {
    const result = eventData.result as string | undefined;
    return result ? result.slice(0, 120) : "Done";
  }

  if (toolName === "search_web") return `${results.length} URLs found`;
  if (toolName === "scrape_url") {
    const scrapeResults = results.filter((r) => r && r.source === "scrape_url");
    if (scrapeResults.length > 0) {
      const content = scrapeResults[scrapeResults.length - 1].content as string | undefined;
      return `Scraped (${(content?.length ?? 0).toLocaleString()} chars)`;
    }
    return "Page scraped";
  }
  if (toolName === "extract_property") {
    const props = results.filter((r) => r && r.title);
    return `${props.length} properties extracted`;
  }
  return `${results.length} results`;
}

export function useSearch(): UseSearchReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchStartedAt, setSearchStartedAt] = useState<number | null>(null);
  const [searchCompletedAt, setSearchCompletedAt] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const planLinesRef = useRef<string[]>([]);
  const timingRef = useRef<{ started: boolean }>({ started: false });

  const submitQuery = useCallback(async (query: string) => {
    const abort = new AbortController();
    abortRef.current = abort;
    setIsStreaming(true);
    setError(null);
    setSteps([]);
    setSearchStartedAt(null);
    setSearchCompletedAt(null);
    timingRef.current = { started: false };
    planLinesRef.current = [];

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

    setMessages([userMsg, thinkingMsg]);

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
            setSearchCompletedAt(Date.now());
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
            const planEvent = event.plan;
            const executeEvent = event.execute;
            const evaluateEvent = event.evaluate;
            const synthesizeEvent = event.synthesize;

            if (planEvent) {
              if (!timingRef.current.started) {
                timingRef.current.started = true;
                setSearchStartedAt(Date.now());
              }
              planLinesRef.current = parsePlanLines(planEvent.plan);
              const step: StepInfo = {
                id: genId(),
                type: "plan",
                label: "Planning",
                summary: `${planLinesRef.current.length} steps planned`,
                detail: planEvent.plan,
                status: "done",
                startedAt: Date.now(),
              };
              setSteps((prev) => [...prev, step]);
            }

            if (executeEvent) {
              const stepIndex = executeEvent.step_index ?? 0;
              const planLine =
                planLinesRef.current[stepIndex] || `Step ${stepIndex + 1}`;
              const toolName = extractToolName(planLine);
              const isError = !!executeEvent.error;

              const summary = isError
                ? `Error: ${executeEvent.error}`
                : formatExecuteSummary(toolName, executeEvent as unknown as Record<string, unknown>);

              const results = executeEvent.results as Record<string, unknown>[] | undefined;

              let detail = `**${planLine}**`;
              if (executeEvent.error) {
                detail += `\nError: ${executeEvent.error}`;
              } else if (toolName === "search_web" && results) {
                const urls = results
                  .map((r, i) => {
                    const url = typeof r === "string" ? r : (r.url as string) || "";
                    return url ? `${i + 1}. [${url}](${url})` : "";
                  })
                  .filter(Boolean)
                  .join("\n");
                if (urls) detail += `\n${urls}`;
              } else if (toolName === "scrape_url" && results) {
                const scrapeResults = results.filter((r) => r && r.source === "scrape_url");
                if (scrapeResults.length > 0) {
                  const content = scrapeResults[scrapeResults.length - 1].content as string | undefined;
                  const chars = content?.length ?? 0;
                  detail += `\nPage scraped (${chars.toLocaleString()} characters)`;
                } else {
                  detail += "\nPage scraped";
                }
              } else if (toolName === "extract_property" && results) {
                const props = results.filter((r) => r && r.title);
                if (props.length > 0) {
                  const names = props
                    .map((p, i) => `${i + 1}. **${p.title}**${p.price_monthly ? ` — ${p.price_monthly}` : ""}`)
                    .join("\n");
                  detail += `\n${names}`;
                }
              } else if (executeEvent.result) {
                detail += `\n${executeEvent.result.slice(0, 300)}`;
              }

              const step: StepInfo = {
                id: genId(),
                type: "execute",
                label: formatStepLabel("execute", toolName),
                summary,
                detail,
                status: isError ? "error" : "done",
                results,
                toolName,
                startedAt: Date.now(),
              };

              setSteps((prev) => [...prev, step]);
            }

            if (evaluateEvent) {
              const step: StepInfo = {
                id: genId(),
                type: "evaluate",
                label: formatStepLabel("evaluate", undefined, evaluateEvent.decision),
                summary: `Decision: ${evaluateEvent.decision}`,
                detail: `Routing decision: **${evaluateEvent.decision}**`,
                status: "done",
                startedAt: Date.now(),
              };
              setSteps((prev) => [...prev, step]);
            }

            if (synthesizeEvent) {
              const step: StepInfo = {
                id: genId(),
                type: "synthesize",
                label: "Generating answer",
                summary: "Done",
                detail: "",
                status: "done",
                startedAt: Date.now(),
              };
              setSteps((prev) => [...prev, step]);
              setMessages((prev) => {
                const updated = [...prev];
                let assistantIdx = -1;
                for (let i = updated.length - 1; i >= 0; i--) {
                  if (updated[i].role === "assistant") {
                    assistantIdx = i;
                    break;
                  }
                }
                if (assistantIdx >= 0) {
                  updated[assistantIdx] = {
                    ...updated[assistantIdx],
                    content: synthesizeEvent.synthesized_answer,
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
        setSteps((prev) => [
          ...prev,
          {
            id: genId(),
            type: "evaluate",
            label: "Cancelled",
            summary: "Search was cancelled by user.",
            detail: "",
            status: "done",
            startedAt: Date.now(),
          },
        ]);
      } else {
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
        setSteps((prev) => [
          ...prev,
          {
            id: genId(),
            type: "evaluate",
            label: "Error",
            summary: msg,
            detail: msg,
            status: "error",
            startedAt: Date.now(),
          },
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
    setSteps([]);
    setSearchId(null);
    setError(null);
    setSearchStartedAt(null);
    setSearchCompletedAt(null);
    timingRef.current = { started: false };
  }, []);

  return {
    messages,
    steps,
    isStreaming,
    searchId,
    error,
    submitQuery,
    cancelSearch,
    clearMessages,
    searchStartedAt,
    searchCompletedAt,
  };
}
