"use client";

import React, { useRef, useState } from "react";
import {
  Send,
  Square,
  AlertCircle,
  Bot,
  User,
  Loader2,
  ChevronDown,
  ChevronUp,
  BookOpen,
} from "lucide-react";
import { ChatMessage, ChatSource, streamChat } from "@/lib/api";

export interface ChatPanelProps {
  docHash: string;
}

interface MessageWithSources extends ChatMessage {
  id: string;
  sources?: ChatSource[];
}

export function ChatPanel({ docHash }: ChatPanelProps) {
  const [messages, setMessages] = useState<MessageWithSources[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track expanded source index per message: msgId -> Set of source indices
  const [expandedSources, setExpandedSources] = useState<
    Record<string, Record<number, boolean>>
  >({});

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  const toggleSource = (msgId: string, sourceIdx: number) => {
    setExpandedSources((prev) => {
      const msgState = prev[msgId] || {};
      return {
        ...prev,
        [msgId]: {
          ...msgState,
          [sourceIdx]: !msgState[sourceIdx],
        },
      };
    });
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isStreaming) return;

    const trimmed = input.trim();
    if (!trimmed) return;

    if (input.length > 2000) {
      setError("Message exceeds maximum length of 2000 characters.");
      return;
    }

    setError(null);

    const userMessageText = input;
    const userMsg: MessageWithSources = {
      id: `user-${Date.now()}`,
      role: "user",
      content: userMessageText,
    };

    const assistantMsgId = `assistant-${Date.now()}`;
    const initialAssistantMsg: MessageWithSources = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      sources: [],
    };

    // Calculate history to send: last 10 messages matching backend's 5-turn window
    const historyToSend: ChatMessage[] = messages.slice(-10).map((m) => ({
      role: m.role,
      content: m.content,
    }));

    setMessages((prev) => [...prev, userMsg, initialAssistantMsg]);
    setIsStreaming(true);
    setInput("");

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      await streamChat(
        {
          doc_hash: docHash,
          message: userMessageText,
          history: historyToSend,
        },
        {
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId
                  ? { ...msg, content: msg.content + token }
                  : msg
              )
            );
            scrollToBottom();
          },
          onSources: (sources) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMsgId ? { ...msg, sources } : msg
              )
            );
          },
          onDone: () => {
            setIsStreaming(false);
            abortControllerRef.current = null;
            scrollToBottom();
          },
          onError: (errDetail) => {
            setIsStreaming(false);
            abortControllerRef.current = null;
            setError(errDetail);
            setInput(userMessageText); // Retain user input so they can retry
          },
        },
        controller.signal
      );
    } catch (err) {
      setIsStreaming(false);
      abortControllerRef.current = null;
      if (!controller.signal.aborted) {
        const detail =
          err instanceof Error ? err.message : "Failed to stream chat response";
        setError(detail);
        setInput(userMessageText); // Retain user input so they can retry
      }
    }
  };

  return (
    <div
      data-testid="chat-panel"
      className="flex flex-col h-full border border-slate-200 rounded-xl bg-white shadow-sm overflow-hidden"
    >
      {/* Header */}
      <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 flex-shrink-0">
        <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
          <Bot className="w-4 h-4 text-blue-600" />
          Paper Q&A Chat
        </h2>
        {isStreaming && (
          <span className="flex items-center gap-1.5 text-xs text-blue-600 font-medium">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Generating response...
          </span>
        )}
      </div>

      {/* Message List */}
      <div className="flex-1 p-4 sm:p-5 overflow-y-auto space-y-4 min-h-0">
        {messages.length === 0 ? (
          <div
            data-testid="chat-empty-state"
            className="flex flex-col items-center justify-center h-full text-center text-slate-400 p-8"
          >
            <Bot className="w-10 h-10 mb-2 text-slate-300" />
            <p className="text-sm font-medium text-slate-600">
              Ask a question about the paper.
            </p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              Answers are grounded strictly in the uploaded document with page
              citations.
            </p>
          </div>
        ) : (
          messages.map((msg) => {
            const hasSources =
              msg.role === "assistant" &&
              Boolean(msg.sources && msg.sources.length > 0);
            const msgSources = msg.sources || [];
            const msgExpState = expandedSources[msg.id] || {};

            return (
              <div
                key={msg.id}
                className={`flex flex-col gap-2 ${
                  msg.role === "user" ? "items-end" : "items-start"
                }`}
              >
                {/* Message Bubble */}
                <div
                  className={`flex gap-2.5 max-w-[85%] ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 shadow-sm"
                      : "bg-slate-100 text-slate-800 rounded-2xl rounded-tl-sm px-4 py-2.5"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <Bot className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
                  )}
                  {msg.role === "user" && (
                    <User className="w-4 h-4 text-blue-200 mt-0.5 flex-shrink-0" />
                  )}
                  <div className="text-sm whitespace-pre-wrap leading-relaxed inline">
                    <span>
                      {msg.content ||
                        (isStreaming && msg.role === "assistant" ? "..." : "")}
                    </span>

                    {/* Numbered Inline Citation Markers */}
                    {hasSources && (
                      <span className="inline-flex flex-wrap items-center gap-1 ml-1.5 align-baseline">
                        {msgSources.map((_, idx) => {
                          const num = idx + 1;
                          const isExpanded = Boolean(msgExpState[idx]);
                          return (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => toggleSource(msg.id, idx)}
                              aria-label={`Citation [${num}]`}
                              aria-expanded={isExpanded}
                              className={`inline-flex items-center justify-center px-1.5 py-0.2 text-[11px] font-bold rounded transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 ${
                                isExpanded
                                  ? "bg-blue-600 text-white"
                                  : "bg-blue-100 text-blue-800 hover:bg-blue-200"
                              }`}
                            >
                              [{num}]
                            </button>
                          );
                        })}
                      </span>
                    )}
                  </div>
                </div>

                {/* Numbered Sources List beneath the message */}
                {hasSources && (
                  <div
                    data-testid="message-sources"
                    className="w-full max-w-[85%] mt-1 space-y-2 pl-4"
                  >
                    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                      Citations ({msgSources.length})
                    </p>
                    {msgSources.map((source, idx) => {
                      const num = idx + 1;
                      const isExpanded = Boolean(msgExpState[idx]);
                      return (
                        <div
                          key={idx}
                          data-testid={`source-card-${num}`}
                          className="border border-slate-200 rounded-lg p-2.5 bg-white text-xs shadow-sm"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => toggleSource(msg.id, idx)}
                                aria-expanded={isExpanded}
                                aria-label={`Toggle source [${num}]`}
                                className="font-bold text-blue-700 hover:text-blue-900 focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
                              >
                                [{num}]
                              </button>
                              <BookOpen className="w-3.5 h-3.5 text-slate-400" />
                              <span className="font-medium text-slate-700">
                                Source
                              </span>
                              {source.page_number !== null && (
                                <span
                                  data-testid="page-badge"
                                  className="px-1.5 py-0.5 text-[10px] font-semibold bg-blue-100 text-blue-800 rounded"
                                >
                                  Page {source.page_number}
                                </span>
                              )}
                            </div>

                            <button
                              type="button"
                              onClick={() => toggleSource(msg.id, idx)}
                              aria-expanded={isExpanded}
                              className="flex items-center gap-1 text-slate-500 hover:text-slate-800 font-medium transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded"
                            >
                              <span>
                                {isExpanded ? "Hide passage" : "Show passage"}
                              </span>
                              {isExpanded ? (
                                <ChevronUp className="w-3.5 h-3.5" />
                              ) : (
                                <ChevronDown className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>

                          {/* Expanded Passage */}
                          {isExpanded && (
                            <div
                              data-testid="source-passage"
                              className="mt-2.5 pl-3 py-1.5 border-l-2 border-blue-500 bg-slate-50/70 text-slate-700 whitespace-pre-wrap leading-relaxed text-xs rounded-r"
                            >
                              <div className="text-[10px] font-semibold text-slate-500 mb-1">
                                {source.page_number !== null
                                  ? `Passage from Page ${source.page_number}:`
                                  : "Passage:"}
                              </div>
                              {source.snippet}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}

        {/* In-list Error state */}
        {error && (
          <div
            role="alert"
            data-testid="chat-error"
            className="flex items-start gap-2.5 p-3.5 text-xs text-red-700 bg-red-50 border border-red-200 rounded-xl"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600 mt-0.5" />
            <div className="flex-1">
              <span className="font-semibold text-red-800">Chat error: </span>
              <span className="whitespace-pre-wrap">{error}</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form
        onSubmit={handleSubmit}
        className="p-3 sm:p-4 border-t border-slate-100 bg-slate-50/50 flex-shrink-0"
      >
        <div className="relative flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSubmit(e);
              }
            }}
            placeholder={
              isStreaming
                ? "Waiting for response..."
                : "Ask a question about this paper (Enter to send, Shift+Enter for new line)..."
            }
            disabled={isStreaming}
            maxLength={2000}
            rows={2}
            className="flex-1 resize-none rounded-xl border border-slate-200 p-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-400 placeholder:text-slate-400 bg-white"
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={handleStop}
              aria-label="Stop generation"
              className="p-3 bg-red-600 text-white rounded-xl hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 flex items-center justify-center flex-shrink-0"
            >
              <Square className="w-4 h-4 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={isStreaming || !input.trim()}
              aria-label="Send message"
              className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 flex items-center justify-center flex-shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="flex justify-between items-center mt-2 px-1 text-[11px] text-slate-400">
          <span>Answers are strictly grounded in document text</span>
          <span>{input.length}/2000</span>
        </div>
      </form>
    </div>
  );
}
