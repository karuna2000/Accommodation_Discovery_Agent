import { type FormEvent, useRef, useEffect } from "react";
import { useSearch } from "../hooks/useSearch";
import type { ChatMessage } from "../types";

function ChatMessage({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const isAssistant = msg.role === "assistant";
  const isSystem = msg.role === "system";

  const bg = isUser
    ? "bg-blue-600 ml-12"
    : isAssistant
      ? "bg-gray-800 mr-12"
      : isSystem
        ? "bg-gray-900/60 border border-gray-700 text-gray-300 text-sm font-mono"
        : "bg-gray-800";

  const align = isUser ? "items-end" : "items-start";

  return (
    <div className={`flex flex-col ${align} mb-4`}>
      <div className={`rounded-xl px-4 py-3 max-w-[85%] whitespace-pre-wrap ${bg}`}>
        {msg.content}
      </div>
    </div>
  );
}

export default function Chat() {
  const {
    messages,
    isStreaming,
    submitQuery,
    cancelSearch,
    clearMessages,
  } = useSearch();

  const inputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const input = inputRef.current;
    if (!input || !input.value.trim() || isStreaming) return;
    const query = input.value.trim();
    input.value = "";
    submitQuery(query);
  };

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto">
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <h1 className="text-lg font-semibold tracking-tight">
          Accommodation Discovery
        </h1>
        <div className="flex gap-2">
          {isStreaming && (
            <button
              onClick={cancelSearch}
              className="text-sm px-3 py-1.5 rounded-lg bg-red-700 hover:bg-red-600 transition-colors cursor-pointer"
            >
              Cancel
            </button>
          )}
          {messages.length > 0 && (
            <button
              onClick={clearMessages}
              className="text-sm px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 transition-colors cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <p className="text-xl mb-2">🏠</p>
            <p className="text-lg">Find your next place</p>
            <p className="text-sm mt-1">Ask about accommodation in any city</p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-gray-800 p-4 flex gap-3"
      >
        <input
          ref={inputRef}
          type="text"
          placeholder="e.g. Find 2-bedroom apartments in London under £2000"
          disabled={isStreaming}
          className="flex-1 rounded-xl bg-gray-800 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isStreaming}
          className="px-5 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 font-medium transition-colors cursor-pointer"
        >
          Send
        </button>
      </form>
    </div>
  );
}
