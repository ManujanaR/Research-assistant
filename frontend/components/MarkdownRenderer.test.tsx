import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownRenderer, preprocessLaTeX } from "./MarkdownRenderer";
import { SummaryView } from "./SummaryView";
import { ChatPanel } from "./ChatPanel";
import { SummaryResponse } from "@/lib/api";

describe("MarkdownRenderer and Math rendering", () => {
  it("renders inline math with \\(...\\) as KaTeX math markup in the DOM", () => {
    const { container } = render(
      <MarkdownRenderer content={"Here is an inline equation: \\(E = mc^2\\) in text."} />
    );

    const katexElement = container.querySelector(".katex");
    expect(katexElement).not.toBeNull();

    const mathElement = container.querySelector("math");
    expect(mathElement).not.toBeNull();

    const annotation = container.querySelector("annotation");
    expect(annotation?.textContent).toBe("E = mc^2");
  });

  it("renders block math with \\[...\\] as KaTeX display math markup in the DOM", () => {
    const { container } = render(
      <MarkdownRenderer
        content={`Consider the quadratic equation:\n\\[\nx = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}\n\\]\nwhich gives the roots.`}
      />
    );

    const displayElement = container.querySelector(".katex-display");
    expect(displayElement).not.toBeNull();

    const katexElement = container.querySelector(".katex");
    expect(katexElement).not.toBeNull();

    const annotation = container.querySelector("annotation");
    expect(annotation?.textContent).toContain("x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}");
  });

  it("renders standard dollar math delimiters ($...$ and $$...$$)", () => {
    const { container } = render(
      <MarkdownRenderer content={"Inline $a + b = c$ and block:\n\n$$\ny = mx + c\n$$"} />
    );

    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("renders raw HTML strings like <script> as plain text, not executed as DOM elements", () => {
    const maliciousInput =
      'Malicious code: <script>alert("hacked")</script> and <img src="x" onerror="evil()" /> should not execute.';
    const { container } = render(<MarkdownRenderer content={maliciousInput} />);

    // Security rule: No raw HTML elements created
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();

    // The text is rendered as plain text
    expect(container.textContent).toContain('<script>alert("hacked")</script>');
    expect(container.textContent).toContain('<img src="x" onerror="evil()" />');
  });

  it("preprocessLaTeX isolates code blocks so equations inside code blocks are preserved", () => {
    const raw = "Code: `\\(not_math\\)` and block:\n```\n\\[code_block\\]\n```\nand real \\(x=1\\)";
    const processed = preprocessLaTeX(raw);
    expect(processed).toContain("`\\(not_math\\)`");
    expect(processed).toContain("\\[code_block\\]");
    expect(processed).toContain("$x=1$");
  });

  it("renders math notation inside SummaryView sections", () => {
    const mathSummary: SummaryResponse = {
      header: {
        title: "Paper on \\(\\mathcal{O}(n)\\) Complexity",
        authors: "T. Euler",
        abstract: "We prove that \\(e^{i\\pi} + 1 = 0\\).",
      },
      title_authors_abstract: "Title with math",
      problem_statement: "Solving \\[\nf(x) = \\int_0^x t\\,dt\n\\] efficiently.",
      methodology: "Using standard integration techniques.",
      key_results: "Achieved exact equality \\(f(x) = \\frac{1}{2}x^2\\).",
      conclusion: "The method is optimal.",
    };

    const { container } = render(
      <SummaryView summary={mathSummary} isLoading={false} error={null} />
    );

    // Title and abstract in header are expanded by default
    const katexInHeader = container.querySelectorAll(".katex");
    expect(katexInHeader.length).toBeGreaterThan(0);
    expect(container.textContent).toContain("Euler");
  });

  it("renders math notation in ChatPanel message bubbles", () => {
    const mockMessages = [
      {
        id: "msg-1",
        role: "user" as const,
        content: "What is the formula for \\(E\\)?",
      },
      {
        id: "msg-2",
        role: "assistant" as const,
        content: "The energy equation is:\n\\[\nE = mc^2\n\\]\nwhere \\(m\\) is mass and \\(c\\) is the speed of light.",
      },
    ];

    const { container } = render(
      <ChatPanel
        docHash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        messages={mockMessages}
      />
    );

    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
  });
});
