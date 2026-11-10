"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

export function preprocessLaTeX(content: string): string {
  if (!content) return "";
  // Split on code blocks and inline code so code snippets remain untouched
  const parts = content.split(/(```[\s\S]*?```|`[^`\n]*`)/g);
  return parts
    .map((part, index) => {
      // Odd indices are code snippets
      if (index % 2 === 1) return part;
      let res = part;
      // Normalize \[ ... \] to display math with empty lines around for CommonMark flow parsing
      res = res.replace(
        /\\{1,2}\[([\s\S]*?)\\{1,2}\]/g,
        (_, eq) => `\n\n$$\n${eq.trim()}\n$$\n\n`
      );
      // Ensure existing $$ blocks have blank lines around them for CommonMark flow parsing
      res = res.replace(
        /(?:^|\n)\s*\$\$([\s\S]*?)\$\$/g,
        (_, eq) => `\n\n$$\n${eq.trim()}\n$$\n\n`
      );
      // Normalize \( ... \) to inline math
      res = res.replace(
        /\\{1,2}\(([\s\S]*?)\\{1,2}\)/g,
        (_, eq) => `$${eq.trim()}$`
      );
      return res;
    })
    .join("");
}

export interface MarkdownRendererProps {
  content?: string;
  className?: string;
  inline?: boolean;
}

export function MarkdownRenderer({
  content = "",
  className,
  inline = false,
}: MarkdownRendererProps) {
  if (!content) return null;
  const normalized = preprocessLaTeX(content);

  if (inline) {
    return (
      <span className={`markdown-inline ${className || ""}`}>
        <ReactMarkdown
          remarkPlugins={[remarkMath]}
          rehypePlugins={[rehypeKatex]}
          components={{
            p: ({ children }) => <span>{children}</span>,
          }}
        >
          {normalized}
        </ReactMarkdown>
      </span>
    );
  }

  return (
    <div className={`markdown-body break-words ${className || ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          p: ({ children }) => (
            <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-inside mb-2 last:mb-0 space-y-1">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside mb-2 last:mb-0 space-y-1">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          pre: ({ children }) => (
            <pre className="p-3 my-2 rounded-lg bg-surface-pill overflow-x-auto text-xs font-mono border border-border-subtle">
              {children}
            </pre>
          ),
          code: ({ children, className: codeClass }) => (
            <code
              className={`${
                codeClass || ""
              } bg-black/10 dark:bg-white/10 px-1.5 py-0.5 rounded text-xs font-mono`}
            >
              {children}
            </code>
          ),
        }}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
