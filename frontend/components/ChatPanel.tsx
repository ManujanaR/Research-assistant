"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Send,
  Square,
  AlertCircle,
  Bot,
  User,
  Loader2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { ChatMessage, ChatSource, streamChat } from "@/lib/api";
import { SourceCard } from "./SourceCard";
import { MarkdownRenderer } from "./MarkdownRenderer";

export interface MessageWithSources extends ChatMessage {
  id: string;
  sources?: ChatSource[];
}

export type DocumentStatus = "none" | "indexing" | "ready";

export interface ChatPanelProps {
  docHash: string;
  documentStatus?: DocumentStatus;
  onUploadClick?: () => void;
  fileInputRef?: React.RefObject<HTMLInputElement | null>;
  messages?: MessageWithSources[];
  onMessagesChange?: (
    updater:
      | MessageWithSources[]
      | ((prev: MessageWithSources[]) => MessageWithSources[])
  ) => void;
}

export function ChatPanel({
  docHash,
  documentStatus: documentStatusProp,
  onUploadClick,
  fileInputRef,
  messages: controlledMessages,
  onMessagesChange,
}: ChatPanelProps) {
  const effectiveStatus: DocumentStatus =
    documentStatusProp ?? (docHash ? "ready" : "none");

  const [internalMessages, setInternalMessages] = useState<MessageWithSources[]>([]);
  const messages =
    controlledMessages !== undefined ? controlledMessages : internalMessages;

  const setMessages = (
    updater:
      | MessageWithSources[]
      | ((prev: MessageWithSources[]) => MessageWithSources[])
  ) => {
    if (onMessagesChange) {
      onMessagesChange(updater);
    } else {
      setInternalMessages(updater);
    }
  };

  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track expanded citation block per message: msgId -> boolean
  const [expandedCitationBlocks, setExpandedCitationBlocks] = useState<
    Record<string, boolean>
  >({});

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const prevMessagesLengthRef = useRef(messages.length);
  const prevDocHashRef = useRef(docHash);
  const isInitialMountRef = useRef(true);

  // Auto-scroll handler: instant for initial load and document changes, smooth only when new message appended
  useEffect(() => {
    if (isInitialMountRef.current) {
      isInitialMountRef.current = false;
      prevMessagesLengthRef.current = messages.length;
      prevDocHashRef.current = docHash;
      if (messages.length > 0 && typeof messagesEndRef.current?.scrollIntoView === "function") {
        messagesEndRef.current.scrollIntoView({ behavior: "auto" });
      }
      return;
    }

    // Document switch: instant scroll
    if (prevDocHashRef.current !== docHash) {
      prevDocHashRef.current = docHash;
      prevMessagesLengthRef.current = messages.length;
      if (messages.length > 0 && typeof messagesEndRef.current?.scrollIntoView === "function") {
        messagesEndRef.current.scrollIntoView({ behavior: "auto" });
      }
      return;
    }

    // Smooth scroll only when a new message is appended (length increases), checking the last message's role
    if (messages.length > prevMessagesLengthRef.current) {
      const lastMessage = messages[messages.length - 1];
      if (
        lastMessage &&
        (lastMessage.role === "assistant" || lastMessage.role === "user") &&
        typeof messagesEndRef.current?.scrollIntoView === "function"
      ) {
        messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
      }
    }

    prevMessagesLengthRef.current = messages.length;
  }, [messages, docHash]);

  const handleUploadClick = () => {
    if (onUploadClick) {
      onUploadClick();
    } else if (fileInputRef?.current) {
      fileInputRef.current.click();
    } else {
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement | null;
      input?.click();
    }
  };

  const toggleCitationBlock = (msgId: string) => {
    setExpandedCitationBlocks((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
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
    if (isStreaming || effectiveStatus !== "ready" || !docHash) return;

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
      className="flex flex-col h-full border border-border-subtle rounded-2xl bg-surface-panel shadow-sm overflow-hidden transition-colors duration-150"
    >
      {/* Header */}
      <div className="px-4 sm:px-5 py-3 border-b border-border-subtle flex items-center justify-between bg-surface-panel flex-shrink-0">
        <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Bot className="w-4 h-4 text-blue-600 dark:text-accent-blue" />
          Paper Q&A Chat
        </h2>
        {isStreaming && (
          <span className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-accent-blue font-medium">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Generating response...
          </span>
        )}
      </div>

      {/* Message List */}
      <div
        data-testid="chat-messages-container"
        className="flex-1 p-3.5 sm:p-5 overflow-y-auto space-y-4 min-h-0 bg-bg-base/40"
      >
        {messages.length > 0 ? (
          messages.map((msg) => {
            const hasSources =
              msg.role === "assistant" &&
              Boolean(msg.sources && msg.sources.length > 0);
            const msgSources = msg.sources || [];
            const isBlockExpanded = Boolean(expandedCitationBlocks[msg.id]);

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
                      : "bg-surface-elevated text-text-primary border border-border-subtle rounded-2xl rounded-tl-sm px-4 py-2.5 shadow-sm"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <Bot className="w-4 h-4 text-text-secondary mt-0.5 flex-shrink-0" />
                  )}
                  {msg.role === "user" && (
                    <User className="w-4 h-4 text-blue-200 mt-0.5 flex-shrink-0" />
                  )}
                  <div className="text-sm leading-relaxed min-w-0 flex-1">
                    {msg.content ? (
                      <MarkdownRenderer content={msg.content} />
                    ) : (
                      <span>
                        {isStreaming && msg.role === "assistant" ? "..." : ""}
                      </span>
                    )}
                  </div>
                </div>

                {/* Citation block beneath the message */}
                {hasSources && (
                  <div
                    data-testid="citation-block"
                    className="w-full max-w-[85%] mt-1 pl-3 sm:pl-4"
                  >
                    <button
                      type="button"
                      onClick={() => toggleCitationBlock(msg.id)}
                      aria-expanded={isBlockExpanded}
                      className="flex items-center gap-1.5 text-xs font-semibold text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-blue rounded py-1 px-1.5"
                    >
                      <span>Sources ({msgSources.length})</span>
                      {isBlockExpanded ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {isBlockExpanded && (
                      <div
                        data-testid="message-sources"
                        className="mt-2 space-y-2"
                      >
                        {msgSources.map((source, idx) => (
                          <SourceCard
                            key={idx}
                            source={source}
                            index={idx}
                            initiallyExpanded={true}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        ) : effectiveStatus === "none" ? (
          <div
            data-testid="chat-zero-state"
            className="flex flex-col items-center justify-center h-full min-h-0 text-center p-6"
          >
            {/* Desktop Zero-State: clean guidance line with high contrast */}
            <div
              data-testid="chat-desktop-zero-state"
              className="hidden lg:flex flex-col items-center justify-center max-w-md mx-auto"
            >
              <p className="text-sm sm:text-base font-medium text-slate-700 dark:text-slate-300 leading-relaxed">
                Upload a research paper from the sidebar to begin analysis and Q&A.
              </p>
            </div>

            {/* Mobile & Compact Zero-State: centered card with upload button */}
            <div
              data-testid="chat-upload-card"
              className="lg:hidden max-w-sm w-full bg-surface-elevated border border-border-subtle rounded-2xl p-6 sm:p-8 shadow-sm flex flex-col items-center text-center"
            >
              <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-accent-blue/10 text-blue-600 dark:text-accent-blue flex items-center justify-center mb-4 border border-blue-100 dark:border-accent-blue/20">
                <UploadCloud className="w-6 h-6" />
              </div>
              <h3 className="text-base sm:text-lg font-semibold text-text-primary mb-2">
                Upload a Research Paper
              </h3>
              <p className="text-sm text-text-secondary mb-6 leading-relaxed">
                A research paper must be uploaded before questions can be asked.
              </p>
              <button
                type="button"
                onClick={handleUploadClick}
                aria-label="Upload Research Paper"
                data-testid="upload-research-paper-button"
                className="inline-flex lg:hidden items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white dark:bg-accent-blue dark:hover:bg-blue-400 dark:text-black font-semibold text-sm transition-all focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-black shadow-sm active:scale-95"
              >
                <UploadCloud className="w-4 h-4" />
                Upload Research Paper
              </button>
            </div>
          </div>
        ) : effectiveStatus === "indexing" ? (
          <div
            data-testid="chat-indexing-state"
            className="flex flex-col items-center justify-center h-full min-h-0 text-center text-text-muted p-6"
          >
            <Loader2 className="w-8 h-8 animate-spin text-blue-600 dark:text-accent-blue mb-3" />
            <h3 className="text-base font-semibold text-text-primary mb-1">
              Indexing paper chunks...
            </h3>
            <p className="text-sm font-medium text-text-secondary">
              Please wait while the document is indexed.
            </p>
          </div>
        ) : (
          <div
            data-testid="chat-empty-state"
            className="flex flex-col items-center justify-center h-full min-h-0 text-center text-text-muted p-6"
          >
            <div className="text-4xl mb-3">👋</div>
            <h3 className="text-lg font-semibold text-text-primary mb-1">
              Let&apos;s start your Research...
            </h3>
            <p className="text-sm font-medium text-text-secondary">
              Ask a question about the paper.
            </p>
            <p className="text-xs text-text-muted mt-1 max-w-xs">
              Answers are grounded strictly in the uploaded document with page
              citations.
            </p>
          </div>
        )}

        {/* In-list Error state */}
        {error && (
          <div
            role="alert"
            data-testid="chat-error"
            className="flex items-start gap-2.5 p-3.5 text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-xl"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
            <div className="flex-1">
              <span className="font-semibold text-red-800 dark:text-red-200">
                Chat error:{" "}
              </span>
              <span className="whitespace-pre-wrap">{error}</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <form
        onSubmit={handleSubmit}
        className="p-2.5 sm:p-4 border-t border-border-subtle bg-surface-panel flex-shrink-0 w-full"
      >
        <div className="relative flex items-end gap-2 w-full">
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
                : effectiveStatus === "none"
                ? "Upload a research paper first to ask questions..."
                : effectiveStatus === "indexing"
                ? "Indexing paper chunks, please wait..."
                : "Ask any question about this paper..."
            }
            disabled={isStreaming || effectiveStatus !== "ready"}
            maxLength={2000}
            rows={2}
            className="flex-1 min-w-0 resize-none rounded-2xl border border-border-subtle p-2.5 sm:p-3 text-base sm:text-sm focus:border-accent-blue focus:outline-none focus:ring-1 focus:ring-accent-blue disabled:bg-surface-elevated disabled:text-slate-600 dark:disabled:text-slate-300 placeholder:text-slate-500 dark:placeholder:text-slate-400 bg-surface-panel text-text-primary shadow-sm"
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={handleStop}
              aria-label="Stop generation"
              className="p-3 bg-red-600 hover:bg-red-700 text-white rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 flex items-center justify-center flex-shrink-0 min-h-[44px] min-w-[44px] shadow-sm"
            >
              <Square className="w-4 h-4 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={isStreaming || effectiveStatus !== "ready" || !input.trim()}
              aria-label="Send message"
              className="p-3 bg-blue-600 hover:bg-blue-700 dark:bg-accent-blue dark:hover:bg-blue-400 dark:text-black disabled:opacity-50 disabled:hover:bg-blue-600 dark:disabled:hover:bg-accent-blue text-white rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 flex items-center justify-center flex-shrink-0 min-h-[44px] min-w-[44px] shadow-sm"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="flex justify-between items-center mt-2 px-1 text-[11px] text-text-muted min-w-0">
          <div className="flex items-center gap-2 truncate mr-2 min-w-0">
            {docHash ? (
              <span className="hidden xs:inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-pill border border-border-subtle text-text-secondary font-medium flex-shrink-0">
                <Sparkles className="w-3 h-3 text-accent-blue" />
                1 document indexed
              </span>
            ) : null}
            <span className="hidden sm:inline truncate">
              Strictly Depend on Uploaded PDF
            </span>
          </div>
          <span className="flex-shrink-0 font-mono text-[11px] ml-auto">{input.length}/2000</span>
        </div>
      </form>
    </div>
  );
}
