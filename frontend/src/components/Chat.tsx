import { type FormEvent, useRef, useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSearch } from "@/hooks/useSearch";
import type { ChatMessage as ChatMessageType, StepInfo } from "@/types";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

/* ───────────────────────────────────────────
   Empty State
   ─────────────────────────────────────────── */
function EmptyState({ onSelect }: { onSelect: (q: string) => void }) {
  const suggestions = [
    "Find 2 BHK flats for rent in Mansarovar, Jaipur under ₹15,000",
    "Studio apartments near UCLA under $2000",
    "Paying guest accommodations for boys near Celebal Technologies",
    "1 BHK for rent in HSR Layout Bangalore under ₹12,000",
  ];
  return (
    <div className="flex flex-col items-center justify-center h-full text-muted-foreground px-6">
      <div className="text-5xl mb-4">🏠</div>
      <h2 className="text-xl font-semibold text-foreground mb-2">
        Find your next place
      </h2>
      <p className="text-sm text-muted-foreground mb-6 text-center max-w-md">
        Ask about accommodation in any city. I&apos;ll search the web, scrape
        listings, and summarize the best options for you.
      </p>
      <div className="space-y-2 w-full max-w-lg">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onSelect(s)}
            className="w-full text-left text-sm px-4 py-3 rounded-xl border border-border 
                       bg-card hover:bg-muted transition-colors text-muted-foreground hover:text-foreground cursor-pointer"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────
   User Bubble
   ─────────────────────────────────────────── */
function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end mb-3">
      <div
        className="max-w-[75%] rounded-2xl px-4 py-2.5 bg-primary text-primary-foreground text-sm leading-relaxed"
        style={{ wordBreak: "break-word" }}
      >
        {content}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────
   Assistant Bubble (Markdown)
   ─────────────────────────────────────────── */
function AssistantBubble({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  if (!content && isStreaming) {
    return (
      <div className="flex items-start gap-3 mb-3">
        <Avatar size="sm">
          <AvatarFallback className="bg-emerald-600 text-white text-xs">
            AI
          </AvatarFallback>
        </Avatar>
        <div className="flex gap-1.5 px-4 py-3">
          <span className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="w-2 h-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>
    );
  }

  if (!content) return null;

  return (
    <div className="flex items-start gap-3 mb-3">
      <Avatar size="sm">
        <AvatarFallback className="bg-emerald-600 text-white text-xs">
          AI
        </AvatarFallback>
      </Avatar>
      <div
        className="max-w-none text-foreground leading-relaxed text-sm
                    [&>p]:my-1 [&>ul]:my-1 [&>ol]:my-1
                    [&>h1]:text-lg [&>h2]:text-base [&>h3]:text-sm
                    [&>h1]:mt-3 [&>h2]:mt-2 [&>h3]:mt-2
                    [&>h1]:mb-1 [&>h2]:mb-1 [&>h3]:mb-1
                    [&_li]:my-0.5
                    [&_a]:text-blue-400 [&_a]:underline
                    [&_code]:bg-muted [&_code]:px-1 [&_code]:rounded"
        style={{ wordBreak: "break-word" }}
      >
        <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────
   Property Card
   ─────────────────────────────────────────── */
function PropertyCard({ data }: { data: Record<string, unknown> }) {
  const [imgError, setImgError] = useState(false);
  const title = (data.title as string) || "Unknown Property";
  const price = (data.price_monthly as string) || (data.price as string) || "";
  const bedrooms = (data.bedrooms as string) || "";
  const location = (data.location as string) || "";
  const amenities = data.amenities as string | string[] | undefined;
  const tags = data.tags as string | string[] | undefined;
  const rating = data.rating as number | undefined;
  const imageUrl = data.images as string | string[] | undefined;
  const sourceUrl = data.source_url as string | undefined;

  const amenityList = Array.isArray(amenities)
    ? amenities
    : typeof amenities === "string"
      ? amenities.split(/[,;]/).map((a) => a.trim()).filter(Boolean)
      : [];

  const tagList = Array.isArray(tags)
    ? tags
    : typeof tags === "string"
      ? tags.split(/[,;]/).map((t) => t.trim()).filter(Boolean)
      : [];

  const firstImage = Array.isArray(imageUrl) ? imageUrl[0] : imageUrl;
  const isValidImage =
    typeof firstImage === "string" &&
    (firstImage.startsWith("http://") || firstImage.startsWith("https://")) &&
    !firstImage.includes("data:image") &&
    !firstImage.includes("pixel");

  return (
    <Card size="sm" className={`my-2 ${isValidImage && !imgError ? "pt-0" : ""}`}>
      {isValidImage && !imgError && (
        <div className="h-36 bg-muted overflow-hidden rounded-t-xl">
          <img
            src={firstImage}
            alt={title}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        </div>
      )}
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {(price || bedrooms) && (
          <div className="flex items-center gap-3 text-sm">
            {price && (
              <span className="text-emerald-400 font-medium">{price}</span>
            )}
            {bedrooms && (
              <span className="text-muted-foreground">🛏️ {bedrooms}</span>
            )}
          </div>
        )}
        {location && (
          <div className="text-xs text-muted-foreground flex items-center gap-1">
            <span>📍</span> {location}
          </div>
        )}
        {amenityList.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {amenityList.slice(0, 5).map((a) => (
              <Badge key={a} variant="secondary" className="text-xs">
                {a}
              </Badge>
            ))}
          </div>
        )}
        {tagList.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tagList.slice(0, 4).map((t) => (
              <span
                key={t}
                className="text-xs px-2 py-0.5 rounded-md bg-blue-900/40 text-blue-300 border border-blue-800"
              >
                {t}
              </span>
            ))}
          </div>
        )}
        {rating !== undefined && rating > 0 && (
          <div className="text-xs text-amber-400">
            ⭐ {rating.toFixed(1)}
          </div>
        )}
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-400 hover:text-blue-300 underline inline-block"
          >
            View listing →
          </a>
        )}
      </CardContent>
    </Card>
  );
}

/* ───────────────────────────────────────────
   Reasoning Panel — single collapsible showing all steps in a timeline
   ─────────────────────────────────────────── */
const STEP_ICONS: Record<string, string> = {
  plan: "📋",
  execute: "🔧",
  evaluate: "⚡",
  synthesize: "💬",
};

function StepDetailContent({ step }: { step: StepInfo }) {
  const isPlan = step.type === "plan";
  const isSearch = step.toolName === "search_web";
  const isScrape = step.toolName === "scrape_url";
  const isExtract = step.toolName === "extract_property";
  const isEvaluate = step.type === "evaluate";

  if (isPlan || isEvaluate) {
    return (
      <div className="text-muted-foreground text-xs leading-relaxed [&>p]:my-0.5 [&_code]:bg-muted [&_code]:px-1 [&_code]:rounded">
        <Markdown remarkPlugins={[remarkGfm]}>
          {step.detail || "No details"}
        </Markdown>
      </div>
    );
  }

  if (isSearch && step.results) {
    const urls = step.results
      .map((r) => (typeof r === "string" ? r : (r as Record<string, unknown>).url as string))
      .filter((u): u is string => typeof u === "string" && u.startsWith("http"));
    return (
      <div className="space-y-1">
        {urls.map((url, i) => (
          <a
            key={i}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-xs text-blue-400 hover:text-blue-300 truncate hover:underline"
          >
            {i + 1}. {url}
          </a>
        ))}
      </div>
    );
  }

  if (isScrape) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>📄</span> {step.summary}
      </div>
    );
  }

  if (isExtract) {
    return (
      <div className="text-xs text-muted-foreground">
        {step.summary}
      </div>
    );
  }

  return (
    <div className="text-muted-foreground text-xs leading-relaxed [&>p]:my-0.5">
      {step.summary}
    </div>
  );
}

function ReasoningStepRow({ step }: { step: StepInfo }) {
  const [open, setOpen] = useState(false);
  const isError = step.status === "error";
  const statusIcon = isError ? "❌" : step.status === "done" ? "✅" : "⏳";
  const icon = STEP_ICONS[step.type] || "•";
  const hasProperties =
    step.toolName === "extract_property" &&
    step.results?.some((r) => r && r.title);

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        className="w-full flex items-center gap-2 py-1.5 px-1 rounded hover:bg-muted/50 transition-colors cursor-pointer text-left"
      >
        <span className="text-xs">{statusIcon}</span>
        <span className="shrink-0">{icon}</span>
        <span className="text-sm text-foreground truncate">{step.label}</span>
        <span className="text-xs text-muted-foreground truncate hidden sm:inline">· {step.summary}</span>
        <svg
          className={`w-3 h-3 ml-auto text-muted-foreground shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden transition-all duration-200 data-[panel-open]:animate-in data-[panel-closed]:animate-out data-[panel-closed]:fade-out-0 data-[panel-open]:fade-in-0 data-[panel-closed]:slide-out-to-top-1 data-[panel-open]:slide-in-from-top-1">
        <div className="ml-5 pl-3 border-l-2 border-border py-1 space-y-2">
          <StepDetailContent step={step} />
          {hasProperties &&
            step.results
              ?.filter((r) => r && r.title)
              .map((r, i) => (
                <PropertyCard key={i} data={r as Record<string, unknown>} />
              ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function ReasoningPanel({ steps, isStreaming }: { steps: StepInfo[]; isStreaming: boolean }) {
  const [open, setOpen] = useState(true);

  const doneCount = steps.filter((s) => s.status === "done").length;
  const errorCount = steps.filter((s) => s.status === "error").length;
  const summary = errorCount > 0
    ? `${steps.length} steps · ${errorCount} error${errorCount > 1 ? "s" : ""}`
    : `${doneCount}/${steps.length} steps`;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-3 border border-border rounded-lg bg-card/30">
      <CollapsibleTrigger className="w-full flex items-center gap-2 px-3 py-2 cursor-pointer">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm">🧠</span>
          <span className="text-sm font-medium text-foreground">Agent thinking</span>
          <Badge variant="secondary" className="text-[10px]">
            {summary}
          </Badge>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {isStreaming && (
            <span className="flex gap-0.5">
              <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "300ms" }} />
            </span>
          )}
          <svg
            className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden transition-all duration-200 data-[panel-open]:animate-in data-[panel-closed]:animate-out data-[panel-closed]:fade-out-0 data-[panel-open]:fade-in-0">
        <div className="px-3 pb-2 space-y-0.5">
          {steps.map((step) => (
            <ReasoningStepRow key={step.id} step={step} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

/* ───────────────────────────────────────────
   Message Dispatcher
   ─────────────────────────────────────────── */
function ChatMessage({
  msg,
  isStreaming,
}: {
  msg: ChatMessageType;
  isStreaming: boolean;
}) {
  if (msg.role === "user") return <UserBubble content={msg.content} />;
  if (msg.role === "assistant") {
    return <AssistantBubble content={msg.content} isStreaming={isStreaming} />;
  }
  return null;
}

/* ───────────────────────────────────────────
   Input Bar
   ─────────────────────────────────────────── */
function InputBar({
  onSubmit,
  disabled,
}: {
  onSubmit: (query: string) => void;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!disabled) inputRef.current?.focus();
  }, [disabled]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const input = inputRef.current;
    if (!input || !input.value.trim() || disabled) return;
    onSubmit(input.value.trim());
    input.value = "";
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-border p-3 md:p-4">
      <div className="flex gap-2 max-w-3xl mx-auto">
        <Input
          ref={inputRef}
          type="text"
          placeholder="Describe the accommodation you're looking for..."
          disabled={disabled}
          className="flex-1 h-10 px-4 text-sm"
        />
        <Button
          type="submit"
          disabled={disabled}
          variant="default"
          className="h-10 px-5 gap-2"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
            />
          </svg>
          <span className="hidden sm:inline">Send</span>
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground text-center mt-2">
        AI-powered accommodation search · Results may not be exhaustive
      </p>
    </form>
  );
}

/* ───────────────────────────────────────────
   Main Chat Component
   ─────────────────────────────────────────── */
export default function Chat() {
  const {
    messages,
    steps,
    isStreaming,
    error,
    submitQuery,
    cancelSearch,
    clearMessages,
  } = useSearch();

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, steps]);

  const hasReasoning = steps.length > 0;

  const userMessages = messages.filter((m) => m.role === "user");
  const assistantMessages = messages.filter((m) => m.role === "assistant");
  const isAssistantEmpty =
    assistantMessages.length === 0 ||
    assistantMessages.every((m) => !m.content);

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-card/80 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <span className="text-lg">🏠</span>
          <h1 className="text-base font-semibold tracking-tight text-foreground">
            Accommodation Discovery
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <span className="text-xs text-destructive hidden md:inline">
              {error}
            </span>
          )}
          {isStreaming && (
            <Button onClick={cancelSearch} variant="destructive" size="sm">
              Stop
            </Button>
          )}
          {messages.length > 0 && !isStreaming && (
            <Button onClick={clearMessages} variant="outline" size="sm">
              New search
            </Button>
          )}
        </div>
      </header>

      {/* Messages */}
      <ScrollArea className="flex-1">
        <div className="px-3 md:px-6 py-4 max-w-3xl mx-auto">
          {messages.length === 0 ? (
            <EmptyState onSelect={submitQuery} />
          ) : (
            <>
              {/* User messages first */}
              {userMessages.map((msg) => (
                <ChatMessage key={msg.id} msg={msg} isStreaming={false} />
              ))}

              {/* Reasoning panel between user and assistant */}
              {hasReasoning && (
                <ReasoningPanel steps={steps} isStreaming={isStreaming} />
              )}

              {/* Assistant messages last */}
              {assistantMessages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  msg={msg}
                  isStreaming={isStreaming && isAssistantEmpty}
                />
              ))}

              <div ref={bottomRef} />
            </>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <InputBar onSubmit={submitQuery} disabled={isStreaming} />
    </div>
  );
}
