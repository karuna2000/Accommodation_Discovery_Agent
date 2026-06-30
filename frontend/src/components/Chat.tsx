import { type FormEvent, useRef, useEffect, useState, useMemo } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSearch } from "@/hooks/useSearch";
import type { ChatMessage as ChatMessageType, StepInfo } from "@/types";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Icon } from "@/components/ui/Icon";
import { GlassPanel } from "@/components/ui/GlassPanel";

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
    <div className="flex flex-col items-center justify-center h-full relative overflow-hidden px-6">
      {/* Ambient glows */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-primary-container/5 rounded-full blur-3xl pointer-events-none" />
      <div className="flex flex-col items-center z-10 relative mt-[-10vh]">
        {/* Glass icon block */}
        <div className="w-16 h-16 rounded-2xl glass-hud flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(173,198,255,0.1)]">
          <Icon name="holiday_village" size={32} fill className="text-primary" />
        </div>
        <h1 className="text-[48px] leading-[56px] tracking-tight font-bold text-foreground text-center mb-4">
          Find your next place
        </h1>
        <p className="text-[18px] leading-[28px] text-muted-foreground text-center max-w-2xl mb-12">
          Ask about accommodation in any city. I&apos;ll search the web, scrape
          listings, and summarize the best options for you.
        </p>
        {/* Suggestion chips */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-[800px]">
          {suggestions.map((s) => (
            <GlassPanel
              key={s}
              as="button"
              onClick={() => onSelect(s)}
              className="p-4 text-left hover:bg-surface-variant/50 transition-colors duration-200 group flex items-start space-x-3 cursor-pointer"
            >
              <Icon name="search" size={20} className="text-outline mt-0.5 group-hover:text-primary transition-colors shrink-0" />
              <span className="text-[16px] leading-[24px] text-muted-foreground group-hover:text-foreground transition-colors">
                {s}
              </span>
            </GlassPanel>
          ))}
        </div>
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
        className="max-w-[75%] rounded-2xl rounded-tr-none px-4 py-2.5 glass-hud text-foreground text-sm leading-relaxed"
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
        <div className="w-8 h-8 rounded-full bg-primary-container shrink-0 flex items-center justify-center">
          <Icon name="smart_toy" size={18} className="text-[#00285d]" />
        </div>
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
      <div className="w-8 h-8 rounded-full bg-primary-container shrink-0 flex items-center justify-center">
        <Icon name="smart_toy" size={18} className="text-[#00285d]" />
      </div>
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
   Property Card — UICODE glass-morphism
   ─────────────────────────────────────────── */
const AMENITY_ICONS: Record<string, string> = {
  ac: "ac_unit",
  "a/c": "ac_unit",
  wifi: "wifi",
  laundry: "local_laundry_service",
  food: "restaurant",
  "power backup": "power",
  power: "power",
  parking: "local_parking",
  security: "security",
  gym: "fitness_center",
  tv: "tv",
  fridge: "kitchen",
  geyser: "water_heater",
  cleaning: "cleaning_services",
  washing: "local_laundry_service",
  elevator: "elevator",
  balcony: "balcony",
};

function PropertyCard({ data }: { data: Record<string, unknown> }) {
  const [imgError, setImgError] = useState(false);
  const title = (data.title as string) || "Unknown Property";
  const price = (data.price_monthly as string) || (data.price as string) || "";
  const locationRaw = data.location;
  const location = locationRaw
    ? typeof locationRaw === "string"
      ? locationRaw
      : (locationRaw as Record<string, unknown>).address as string || ""
    : "";
  const amenities = data.amenities as string | string[] | undefined;
  const imageUrl = data.images as string | string[] | undefined;
  const sourceUrl = data.source_url as string | undefined;

  const amenityList = Array.isArray(amenities)
    ? amenities
    : typeof amenities === "string"
      ? amenities.split(/[,;]/).map((a) => a.trim()).filter(Boolean)
      : [];

  const firstImage = Array.isArray(imageUrl) ? imageUrl[0] : imageUrl;
  const isValidImage =
    typeof firstImage === "string" &&
    (firstImage.startsWith("http://") || firstImage.startsWith("https://")) &&
    !firstImage.includes("data:image") &&
    !firstImage.includes("pixel");

  return (
    <div className="bg-surface-container-low border border-border-subtle rounded-xl overflow-hidden hover:shadow-lg hover:shadow-primary/5 transition-all duration-200 group flex flex-col my-2">
      <div className="h-36 w-full relative overflow-hidden bg-surface-variant">
        {isValidImage && !imgError && (
          <img
            src={firstImage}
            alt={title}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        )}
      </div>
      <div className="p-4 flex flex-col flex-grow">
        <div className="flex justify-between items-start mb-2">
          <div className="min-w-0">
            <h3 className="text-[20px] leading-[28px] font-semibold text-foreground truncate">{title}</h3>
            {location && (
              <p className="text-[12px] leading-[16px] text-muted-foreground mt-0.5 truncate">{location}</p>
            )}
          </div>
          <div className="text-right shrink-0 ml-2">
            {price && (
              <>
                <span className="text-[20px] leading-[28px] font-semibold text-primary">{price}</span>
                <span className="text-[12px] leading-[16px] text-muted-foreground block">/month</span>
              </>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 mt-auto pt-3">
          {amenityList.slice(0, 5).map((a) => {
            const iconName = AMENITY_ICONS[a.toLowerCase().trim()] || "check_circle";
            return (
              <span
                key={a}
                className="px-2 py-1 rounded-md border border-border-subtle text-[12px] leading-[16px] text-muted-foreground flex items-center gap-1"
              >
                <Icon name={iconName} size={14} className="text-muted-foreground" />
                <span>{a}</span>
              </span>
            );
          })}
        </div>
        {sourceUrl && (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[12px] leading-[16px] text-blue-400 hover:text-blue-300 underline mt-2 inline-block"
          >
            View listing →
          </a>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────
   Reasoning Panel — UICODE glass-morphism with progress bar + source list
   ─────────────────────────────────────────── */
function SourceRow({
  url,
  status,
}: {
  url: string;
  status: "done" | "error" | "running";
}) {
  const displayUrl = url.startsWith("http")
    ? url.replace(/^https?:\/\//, "").replace(/\/.*$/, "")
    : url;

  return (
    <div className="flex items-center justify-between bg-surface-variant/20 p-2 rounded-md border border-border-subtle">
      <div className="flex items-center gap-2 min-w-0">
        <Icon name="language" size={16} className="text-primary shrink-0" />
        <span className="text-[14px] leading-[20px] text-foreground truncate">
          {displayUrl}
        </span>
      </div>
      <span
        className={`shrink-0 ml-2 px-1.5 py-0.5 rounded text-[12px] leading-[16px] font-medium border ${
          status === "error"
            ? "bg-error-rose/10 text-error-rose border-error-rose/20"
            : status === "running"
              ? "bg-primary/10 text-primary border-primary/20 animate-pulse"
              : "bg-success/10 text-success border-success/20"
        }`}
      >
        {status === "error" ? "Error" : status === "running" ? "Analyzing..." : "Complete"}
      </span>
    </div>
  );
}

function ReasoningPanel({
  steps,
  isStreaming,
  searchStartedAt,
  searchCompletedAt,
}: {
  steps: StepInfo[];
  isStreaming: boolean;
  searchStartedAt: number | null;
  searchCompletedAt: number | null;
}) {
  const [open, setOpen] = useState(true);
  const [snippetOpen, setSnippetOpen] = useState(false);

  const doneCount = steps.filter((s) => s.status === "done").length;
  const errorCount = steps.filter((s) => s.status === "error").length;
  const progressPct = steps.length > 0 ? (doneCount / steps.length) * 100 : 0;
  const allDone = doneCount === steps.length && steps.length > 0;
  const isComplete = !isStreaming && !!searchCompletedAt;

  const elapsedMs =
    searchStartedAt && searchCompletedAt
      ? searchCompletedAt - searchStartedAt
      : searchStartedAt
        ? Date.now() - searchStartedAt
        : 0;
  const elapsedSeconds = (elapsedMs / 1000).toFixed(1);

  const sources = useMemo(() => {
    const result: { url: string; status: "done" | "error" | "running" }[] = [];
    for (const step of steps) {
      if (step.type === "execute" && step.toolName === "search_web" && step.results) {
        for (const r of step.results) {
          const url = typeof r === "string" ? r : (r.url as string) || (r.result as string) || "";
          if (url && url.startsWith("http")) {
            result.push({ url, status: step.status === "error" ? "error" : "done" });
          }
        }
      }
    }
    if (isStreaming && !allDone) {
      result.push({ url: "Next source...", status: "running" });
    }
    return result;
  }, [steps, isStreaming, allDone]);

  const scrapeSteps = useMemo(
    () => steps.filter((s) => s.toolName === "scrape_url" && s.detail),
    [steps],
  );

  return (
    <div className="w-full bg-surface-container-low/40 border border-border-subtle rounded-xl overflow-hidden mb-3">
      {/* Progress bar */}
      <div className="h-1 w-full bg-surface-variant">
        <div
          className="h-full transition-all duration-500 ease-out"
          style={{
            width: `${progressPct}%`,
            backgroundColor: errorCount > 0 ? "var(--error-rose)" : "var(--success)",
          }}
        />
      </div>

      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-surface-variant/20 transition-colors group cursor-pointer">
          <div className="flex items-center gap-3">
            <Icon
              name={isComplete ? "check_circle" : "search"}
              size={18}
              fill
              className={isComplete ? "text-success" : "text-primary"}
            />
            <div className="flex flex-col items-start">
              <span className="text-[14px] leading-[20px] font-semibold text-foreground">
                {isComplete ? "Search completed" : isStreaming ? "Analyzing..." : "Search results"}
              </span>
              <span className="text-[12px] leading-[16px] text-muted-foreground/70">
                {sources.length > 0 ? `${sources.length} source${sources.length > 1 ? "s" : ""}` : ""}
                {sources.length > 0 && elapsedMs > 0 ? ` analyzed in ${elapsedSeconds}s` : ""}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[12px] leading-[16px] text-muted-foreground/50 bg-surface-variant/30 px-1.5 py-0.5 rounded font-mono">
              {doneCount}/{steps.length}
            </span>
            <Icon
              name={open ? "expand_less" : "expand_more"}
              size={20}
              className="text-muted-foreground group-hover:text-foreground transition-colors"
            />
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent className="overflow-hidden transition-all duration-200 data-[panel-open]:animate-in data-[panel-closed]:animate-out data-[panel-closed]:fade-out-0 data-[panel-open]:fade-in-0">
          <div className="border-t border-border-subtle bg-surface-container-lowest/30 p-4 space-y-3">
            {/* Sources searched */}
            {sources.length > 0 && (
              <div className="space-y-2">
                <p className="text-[12px] leading-[16px] font-semibold text-muted-foreground/70 uppercase tracking-wider">
                  Sources Searched
                </p>
                <div className="space-y-2">
                  {sources.map((s, i) => (
                    <SourceRow key={i} url={s.url} status={s.status} />
                  ))}
                </div>
              </div>
            )}

            {/* Scraped snippet (collapsed by default) */}
            {scrapeSteps.length > 0 && (
              <div className="pt-2 border-t border-border-subtle">
                <Collapsible open={snippetOpen} onOpenChange={setSnippetOpen}>
                  <CollapsibleTrigger className="flex items-center gap-2 cursor-pointer group">
                    <Icon
                      name={snippetOpen ? "expand_less" : "expand_more"}
                      size={16}
                      className="text-muted-foreground group-hover:text-foreground transition-colors"
                    />
                    <p className="text-[12px] leading-[16px] font-semibold text-muted-foreground/70 uppercase tracking-wider">
                      Scraped Content Snippet
                    </p>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="mt-2 bg-surface-container-lowest p-3 rounded border border-border-subtle text-[12px] leading-[16px] text-muted-foreground whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {scrapeSteps.map((s) => (
                        <div key={s.id} className="mb-2 last:mb-0">
                          {s.detail}
                        </div>
                      ))}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            )}

            {/* Steps list */}
            <div className="pt-2 border-t border-border-subtle space-y-2">
              {steps.map((step) => {
                const isError = step.status === "error";
                return (
                  <div key={step.id} className="flex items-center justify-between bg-surface-variant/20 p-2 rounded-md border border-border-subtle">
                    <div className="flex items-center gap-2 min-w-0">
                      <Icon
                        name={
                          step.type === "plan"
                            ? "list"
                            : step.type === "evaluate"
                              ? "alt_route"
                              : step.toolName === "search_web"
                                ? "travel_explore"
                                : step.toolName === "scrape_url"
                                  ? "web"
                                  : step.toolName === "extract_property"
                                    ? "database"
                                    : step.type === "synthesize"
                                      ? "psychiatry"
                                      : "radio_button_checked"
                        }
                        size={16}
                        className={
                          isError
                            ? "text-error-rose"
                            : step.type === "synthesize"
                              ? "text-primary"
                              : "text-muted-foreground"
                        }
                      />
                      <span className="text-[14px] leading-[20px] text-foreground truncate">
                        {step.label}
                      </span>
                    </div>
                    <span
                      className={`shrink-0 ml-2 px-1.5 py-0.5 rounded text-[12px] leading-[16px] font-medium border ${
                        isError
                          ? "bg-error-rose/10 text-error-rose border-error-rose/20"
                          : "bg-success/10 text-success border-success/20"
                      }`}
                    >
                      {isError ? "Error" : "Complete"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
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
    <form onSubmit={handleSubmit}>
      <div className="fixed bottom-0 left-0 w-full z-50 bg-gradient-to-t from-background via-background/90 to-transparent pt-10 pb-6 px-4 md:px-6">
        <div className="max-w-[800px] mx-auto">
          <div className="glass-hud rounded-2xl p-2 pl-4 flex items-center focus-within:border-primary/50 focus-within:shadow-[0_0_15px_rgba(173,198,255,0.15)] transition-all duration-300">
            <Icon name="home_work" size={20} className="text-outline mr-2 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Describe the accommodation you're looking for..."
              disabled={disabled}
              className="flex-1 bg-transparent border-none focus:ring-0 text-foreground text-[16px] leading-[24px] placeholder-outline py-3 outline-none"
            />
            <button
              type="submit"
              disabled={disabled}
              className="bg-primary hover:bg-primary-container text-on-primary rounded-xl p-3 ml-2 transition-colors duration-200 flex items-center justify-center disabled:opacity-50"
            >
              <Icon name="send" size={20} fill className="text-on-primary" />
            </button>
          </div>
          <p className="text-center mt-4 text-[12px] leading-[16px] text-outline-variant">
            AI-powered accommodation search · Results may not be exhaustive
          </p>
        </div>
      </div>
    </form>
  );
}

/* ───────────────────────────────────────────
   BottomNavBar — mobile only
   ─────────────────────────────────────────── */
function BottomNavBar() {
  return (
    <nav className="md:hidden glass-hud border-t border-border-subtle fixed bottom-0 w-full z-50 flex justify-around items-center px-4 py-3 rounded-t-xl">
      <a className="flex flex-col items-center justify-center bg-primary-container text-[#00285d] rounded-full px-4 py-1 transition-all duration-200 active:scale-90" href="#">
        <Icon name="search" size={20} fill />
        <span className="text-[14px] leading-[20px] mt-1">Search</span>
      </a>
    </nav>
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
    searchStartedAt,
    searchCompletedAt,
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

  const extractedProperties = useMemo(() => {
    const props: Record<string, unknown>[] = [];
    for (const step of steps) {
      if (step.toolName === "extract_property" && step.results) {
        for (const r of step.results) {
          if (r && r.title) props.push(r as Record<string, unknown>);
        }
      }
    }
    return props;
  }, [steps]);

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-background z-50 relative">
        <div className="flex items-center gap-3">
          <Icon name="holiday_village" size={24} fill className="text-primary" />
          <h1 className="text-[24px] md:text-[32px] leading-[32px] md:leading-[40px] tracking-tight font-semibold text-foreground">
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
          <button className="text-muted-foreground hover:text-foreground transition-colors p-2">
            <Icon name="settings" size={20} />
          </button>
        </div>
      </header>

      {/* Messages */}
      <ScrollArea className="flex-1">
        <div className="px-3 md:px-6 py-4 max-w-[800px] mx-auto pb-36">
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
                <ReasoningPanel
                  steps={steps}
                  isStreaming={isStreaming}
                  searchStartedAt={searchStartedAt}
                  searchCompletedAt={searchCompletedAt}
                />
              )}

              {/* Assistant messages last */}
              {assistantMessages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  msg={msg}
                  isStreaming={isStreaming && isAssistantEmpty}
                />
              ))}

              {/* Property cards grid */}
              {extractedProperties.length > 0 && !isStreaming && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                  {extractedProperties.map((p, i) => (
                    <PropertyCard key={i} data={p} />
                  ))}
                </div>
              )}

              <div ref={bottomRef} />
            </>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <InputBar onSubmit={submitQuery} disabled={isStreaming} />

      {/* Bottom nav */}
      <BottomNavBar />
    </div>
  );
}
