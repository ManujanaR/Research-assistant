import React from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";

import { UploadZone } from "./UploadZone";
import { SummaryView } from "./SummaryView";
import { SourceCard } from "./SourceCard";
import { ChatPanel } from "./ChatPanel";
import { ApiError, uploadPdf, streamChat, SummaryResponse } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    uploadPdf: vi.fn(),
    streamChat: vi.fn(),
  };
});

describe("Frontend UI Components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("UploadZone", () => {
    it("renders in idle state", () => {
      render(<UploadZone onUploaded={() => {}} />);
      expect(
        screen.getByText("Click to upload or drag and drop")
      ).toBeDefined();
      expect(
        screen.getByRole("button", { name: /click to upload/i })
      ).toBeDefined();
    });

    it("shows 415-style message without calling uploadPdf when file is text/plain", async () => {
      const onUploaded = vi.fn();
      render(<UploadZone onUploaded={onUploaded} />);

      const file = new File(["not a pdf"], "notes.txt", { type: "text/plain" });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(
          screen.getByText("Invalid file type: only application/pdf is accepted.")
        ).toBeDefined();
      });

      expect(uploadPdf).not.toHaveBeenCalled();
      expect(onUploaded).not.toHaveBeenCalled();
    });

    it("calls uploadPdf once and shows loading, then calls onUploaded for valid PDF", async () => {
      const onUploaded = vi.fn();
      const mockResult = {
        doc_hash: "a".repeat(64),
        filename: "paper.pdf",
        size_bytes: 2048,
        page_count: 5,
        chunk_count: 12,
      };

      vi.mocked(uploadPdf).mockImplementation(
        () =>
          new Promise((resolve) => {
            setTimeout(() => resolve(mockResult), 50);
          })
      );

      render(<UploadZone onUploaded={onUploaded} />);

      const file = new File(["dummy pdf bytes"], "paper.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      expect(
        screen.getByText("Uploading and analyzing research paper...")
      ).toBeDefined();

      await waitFor(() => {
        expect(uploadPdf).toHaveBeenCalledTimes(1);
        expect(onUploaded).toHaveBeenCalledWith(mockResult);
      });
    });

    it("shows server ApiError detail on failure", async () => {
      const errorDetail = "File exceeds maximum allowed size of 20MB.";
      vi.mocked(uploadPdf).mockRejectedValueOnce(new ApiError(413, errorDetail));

      render(<UploadZone onUploaded={() => {}} />);

      const file = new File(["large pdf content"], "paper.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
        expect(screen.getByText(errorDetail)).toBeDefined();
      });
    });
  });

  describe("SummaryView", () => {
    it("renders the loading skeleton when isLoading is true", () => {
      render(
        <SummaryView summary={null} isLoading={true} error={null} />
      );
      expect(screen.getByTestId("summary-loading")).toBeDefined();
    });

    it("renders the empty message when summary is null, not loading, and no error", () => {
      render(
        <SummaryView summary={null} isLoading={false} error={null} />
      );
      expect(screen.getByText("No summary available")).toBeDefined();
      expect(
        screen.getByText(/upload a research paper to generate a structured/i)
      ).toBeDefined();
    });

    it("renders the error text when error is provided", () => {
      const errorMessage = "Failed to load summary: 500 internal server error";
      render(
        <SummaryView summary={null} isLoading={false} error={errorMessage} />
      );
      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText(errorMessage)).toBeDefined();
    });

    it("renders all five sections in order when populated", () => {
      const mockSummary: SummaryResponse = {
        title_authors_abstract: "Attention Is All You Need by Vaswani et al.",
        problem_statement: "Recurrence creates computational bottlenecks.",
        methodology: "Transformer architecture with multi-head self-attention.",
        key_results: "BLEU score of 28.4 on WMT 2014 English-to-German.",
        conclusion: "Self-attention can replace recurrence entirely.",
      };

      render(
        <SummaryView summary={mockSummary} isLoading={false} error={null} />
      );

      const headings = screen.getAllByRole("heading", { level: 3 });
      expect(headings).toHaveLength(5);

      const expectedHeadings = [
        "Title, Authors & Abstract",
        "Problem Statement",
        "Methodology",
        "Key Results",
        "Conclusion",
      ];

      headings.forEach((h, index) => {
        expect(h.textContent?.trim()).toBe(expectedHeadings[index]);
      });

      expect(
        screen.getByText("Attention Is All You Need by Vaswani et al.")
      ).toBeDefined();
      expect(
        screen.getByText("Self-attention can replace recurrence entirely.")
      ).toBeDefined();
    });
  });

  describe("SourceCard", () => {
    it("shows page badge with page number when page_number is not null", () => {
      render(
        <SourceCard
          source={{
            page_number: 2,
            snippet: "Snippet text on page 2",
          }}
        />
      );

      const badge = screen.getByTestId("page-badge");
      expect(badge.textContent).toBe("Page 2");
      expect(badge.textContent).not.toContain("null");
      expect(badge.textContent).not.toContain("undefined");
    });

    it("shows no badge and no text containing null or undefined when page_number is null", () => {
      const { container } = render(
        <SourceCard
          source={{
            page_number: null,
            snippet: "Excerpt without explicit page number",
          }}
        />
      );

      expect(screen.queryByTestId("page-badge")).toBeNull();
      expect(container.textContent).not.toContain("null");
      expect(container.textContent).not.toContain("undefined");
      expect(container.textContent).not.toContain("Page");
    });

    it("snippet is hidden until expand button is pressed, and aria-expanded flips", () => {
      const snippetText = "This is a detailed excerpt from the paper.";
      render(
        <SourceCard
          source={{
            page_number: 1,
            snippet: snippetText,
          }}
        />
      );

      const toggleButton = screen.getByRole("button", { name: /show snippet/i });
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId("source-snippet")).toBeNull();

      fireEvent.click(toggleButton);

      expect(toggleButton.getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByTestId("source-snippet").textContent).toBe(snippetText);

      fireEvent.click(toggleButton);
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId("source-snippet")).toBeNull();
    });
  });

  describe("ChatPanel", () => {
    const docHash = "1234567890abcdef".repeat(4);

    it("empty state shows the prompt", () => {
      render(<ChatPanel docHash={docHash} />);
      expect(
        screen.getByText("Ask a question about the paper.")
      ).toBeDefined();
      expect(screen.getByTestId("chat-empty-state")).toBeDefined();
    });

    it("sending a message with mocked streamChat renders assistant text and source card", async () => {
      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onToken("The core approach ");
        handlers.onToken("uses self-attention.");
        handlers.onSources([
          { page_number: 4, snippet: "Transformer models rely on self-attention." },
        ]);
        handlers.onDone();
      });

      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(/ask a question about this paper/i);
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, { target: { value: "What is the architecture?" } });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByText("What is the architecture?")).toBeDefined();
        expect(
          screen.getByText("The core approach uses self-attention.")
        ).toBeDefined();
        expect(screen.getByTestId("message-sources")).toBeDefined();
        expect(screen.getByText("Page 4")).toBeDefined();
      });

      expect(streamChat).toHaveBeenCalledTimes(1);
    });

    it("whitespace-only input does not call streamChat", () => {
      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(/ask a question about this paper/i);
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, { target: { value: "   \n\t  " } });
      fireEvent.click(sendButton);

      expect(streamChat).not.toHaveBeenCalled();
    });

    it("input over 2000 characters is rejected", () => {
      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(/ask a question about this paper/i);
      const sendButton = screen.getByRole("button", { name: /send message/i });

      const longMessage = "a".repeat(2001);
      fireEvent.change(textarea, { target: { value: longMessage } });
      fireEvent.click(sendButton);

      expect(streamChat).not.toHaveBeenCalled();
      expect(
        screen.getByText("Message exceeds maximum length of 2000 characters.")
      ).toBeDefined();
    });

    it("mocked onError shows error in message list and keeps the input value", async () => {
      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onError("Connection lost while streaming tokens.");
      });

      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      ) as HTMLTextAreaElement;
      const sendButton = screen.getByRole("button", { name: /send message/i });

      const originalQuestion = "What were the baseline models?";
      fireEvent.change(textarea, { target: { value: originalQuestion } });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByTestId("chat-error")).toBeDefined();
        expect(
          screen.getByText("Connection lost while streaming tokens.")
        ).toBeDefined();
      });

      // Retained input for user retry
      expect(textarea.value).toBe(originalQuestion);
    });

    it("stop button aborts the signal passed to streamChat", async () => {
      let passedSignal: AbortSignal | undefined;

      vi.mocked(streamChat).mockImplementation(
        async (_params, handlers, signal) => {
          passedSignal = signal;
          handlers.onToken("Starting generated text...");
          return new Promise<void>((resolve) => {
            signal?.addEventListener("abort", () => {
              resolve();
            });
          });
        }
      );

      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(/ask a question about this paper/i);
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, { target: { value: "Explain the dataset" } });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByText("Starting generated text...")).toBeDefined();
        expect(screen.getByLabelText("Stop generation")).toBeDefined();
      });

      const stopButton = screen.getByLabelText("Stop generation");
      fireEvent.click(stopButton);

      expect(passedSignal?.aborted).toBe(true);
      // Partial assistant message stays in document
      expect(screen.getByText("Starting generated text...")).toBeDefined();
    });
  });
});
