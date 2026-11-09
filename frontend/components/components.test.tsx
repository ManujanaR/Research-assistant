import React from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
  within,
  act,
} from "@testing-library/react";

import { UploadZone } from "./UploadZone";
import { SummaryView } from "./SummaryView";
import { SourceCard } from "./SourceCard";
import { SourcePanel } from "./SourcePanel";
import { StudioPanel } from "./StudioPanel";
import { ChatPanel } from "./ChatPanel";
import { ExportButton } from "./ExportButton";
import { ThemeToggle } from "./ThemeToggle";
import { AuthPanel } from "./AuthPanel";
import { ConvertLink } from "./ConvertLink";
import { CredibilityCard } from "./CredibilityCard";
import { ProfileMenu } from "./ProfileMenu";
import { ProfileForm } from "./ProfileForm";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { HelpButton } from "./HelpButton";
import { HelpPanel } from "./HelpPanel";
import { ViewPdfButton } from "./ViewPdfButton";
import { PdfViewerDrawer } from "./PdfViewerDrawer";
import Home from "@/app/page";
import {
  ApiError,
  uploadPdf,
  getSummary,
  streamChat,
  getMe,
  getProfile,
  updateProfile,
  changePassword,
  signIn,
  signUp,
  signOut,
  exportReport,
  SummaryResponse,
  getDocumentCredibility,
  CredibilityResponse,
} from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    uploadPdf: vi.fn(),
    getSummary: vi.fn(),
    streamChat: vi.fn(),
    getMe: vi.fn(),
    getProfile: vi.fn(),
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    exportReport: vi.fn(),
    getDocumentCredibility: vi.fn(),
  };
});

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe("Frontend UI Components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMe).mockResolvedValue({
      id: "user-1",
      email: "user@example.com",
    });
  });

  afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
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
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement;

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
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement;

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
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
        expect(screen.getByText(errorDetail)).toBeDefined();
      });
    });

    it("shows OCR note when upload response has ocr_used true", async () => {
      const onUploaded = vi.fn();
      const mockResult = {
        doc_hash: "b".repeat(64),
        filename: "scanned.pdf",
        size_bytes: 4096,
        page_count: 3,
        chunk_count: 8,
        ocr_used: true,
      };

      vi.mocked(uploadPdf).mockResolvedValueOnce(mockResult);

      render(<UploadZone onUploaded={onUploaded} />);

      const file = new File(["scanned bytes"], "scanned.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(
          screen.getByText(
            "This paper was read with OCR. Check the summary against the original."
          )
        ).toBeDefined();
      });
    });

    it("does not show OCR note when upload response has ocr_used false or omitted", async () => {
      const onUploaded = vi.fn();
      const mockResult = {
        doc_hash: "c".repeat(64),
        filename: "digital.pdf",
        size_bytes: 4096,
        page_count: 3,
        chunk_count: 8,
        ocr_used: false,
      };

      vi.mocked(uploadPdf).mockResolvedValueOnce(mockResult);

      render(<UploadZone onUploaded={onUploaded} />);

      const file = new File(["digital bytes"], "digital.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement;

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(onUploaded).toHaveBeenCalledWith(mockResult);
      });

      expect(
        screen.queryByText(
          "This paper was read with OCR. Check the summary against the original."
        )
      ).toBeNull();
    });

    it("shows OCR note when ocr_used prop is true and hides when false", () => {
      const { rerender } = render(
        <UploadZone onUploaded={() => {}} ocr_used={true} />
      );
      expect(
        screen.getByText(
          "This paper was read with OCR. Check the summary against the original."
        )
      ).toBeDefined();

      rerender(<UploadZone onUploaded={() => {}} ocr_used={false} />);
      expect(
        screen.queryByText(
          "This paper was read with OCR. Check the summary against the original."
        )
      ).toBeNull();
    });
  });

  describe("SummaryView", () => {
    const mockSummary: SummaryResponse = {
      header: {
        title: "Attention Is All You Need",
        authors: "Vaswani et al.",
        abstract: "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
      },
      title_authors_abstract: "Attention Is All You Need by Vaswani et al.",
      problem_statement: "Recurrence creates computational bottlenecks.",
      methodology: "Transformer architecture with multi-head self-attention.",
      key_results: "BLEU score of 28.4 on WMT 2014 English-to-German.",
      conclusion: "Self-attention can replace recurrence entirely.",
    };

    it("renders the loading skeleton when isLoading is true", () => {
      render(<SummaryView summary={null} isLoading={true} error={null} />);
      expect(screen.getByTestId("summary-loading")).toBeDefined();
    });

    it("renders the empty message when summary is null, not loading, and no error", () => {
      render(<SummaryView summary={null} isLoading={false} error={null} />);
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

    it("renders all five sections with only the first section expanded by default", () => {
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

      // Section 1 is expanded by default with title, authors, and abstract
      expect(screen.getByText("Attention Is All You Need")).toBeDefined();
      expect(screen.getByText("Vaswani et al.")).toBeDefined();
      expect(
        screen.getByText(
          "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks."
        )
      ).toBeDefined();

      // Sections 2-5 are collapsed by default
      expect(
        screen.queryByText("Self-attention can replace recurrence entirely.")
      ).toBeNull();
      expect(
        screen.queryByText("Recurrence creates computational bottlenecks.")
      ).toBeNull();

      // Clicking Conclusion section expands it
      const conclusionCard = screen.getByTestId("summary-card-conclusion");
      const toggle = conclusionCard.querySelector('[role="button"]')!;
      fireEvent.click(toggle);

      expect(
        screen.getByText("Self-attention can replace recurrence entirely.")
      ).toBeDefined();
    });

    it("renders title, authors, and abstract separately in the header card", () => {
      render(
        <SummaryView summary={mockSummary} isLoading={false} error={null} />
      );

      const titleHeading = screen.getByTestId("header-title");
      expect(titleHeading.textContent).toBe("Attention Is All You Need");

      const authorsLine = screen.getByTestId("header-authors");
      expect(authorsLine.textContent).toBe("Vaswani et al.");

      const abstractPara = screen.getByTestId("header-abstract");
      expect(abstractPara.textContent).toBe(
        "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks."
      );
    });

    it("section copy button copies plain text and shows Copied confirmation", async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      render(
        <SummaryView summary={mockSummary} isLoading={false} error={null} />
      );

      const copyBtn = screen.getByRole("button", {
        name: "Copy Title, Authors & Abstract",
      });
      fireEvent.click(copyBtn);

      const expectedText = `${mockSummary.header.title}\n${mockSummary.header.authors}\n\n${mockSummary.header.abstract}`;
      expect(writeTextMock).toHaveBeenCalledWith(expectedText);

      await waitFor(() => {
        expect(screen.getByText("Copied")).toBeDefined();
      });
    });

    it("clipboard failure displays a visible error message", async () => {
      const writeTextMock = vi
        .fn()
        .mockRejectedValue(new Error("Clipboard permission denied"));
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      render(
        <SummaryView summary={mockSummary} isLoading={false} error={null} />
      );

      const copyBtn = screen.getByRole("button", {
        name: "Copy Title, Authors & Abstract",
      });
      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(screen.getByText("Failed to copy")).toBeDefined();
      });
    });
  });

  describe("SourceCard", () => {
    it("shows page badge with page number only when expanded", () => {
      render(
        <SourceCard
          source={{
            page_number: 2,
            snippet: "Snippet text on page 2",
          }}
        />
      );

      // Collapsed initially
      expect(screen.queryByTestId("page-badge")).toBeNull();
      expect(screen.queryByText(/Snippet text on page 2/)).toBeNull();

      const toggleButton = screen.getByRole("button", { name: /show passage/i });
      fireEvent.click(toggleButton);

      const badge = screen.getByTestId("page-badge");
      expect(badge.textContent).toBe("Page 2");
      expect(screen.getByTestId("source-snippet").textContent).toBe(
        "Snippet text on page 2"
      );
    });

    it("shows no badge and no text containing null or undefined when page_number is null", () => {
      const { container } = render(
        <SourceCard
          initiallyExpanded={true}
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
      expect(screen.getByTestId("source-snippet").textContent).toBe(
        "Excerpt without explicit page number"
      );
    });

    it("passage is hidden until expand button is pressed, and aria-expanded flips", () => {
      const snippetText = "This is a detailed excerpt from the paper.";
      render(
        <SourceCard
          source={{
            page_number: 1,
            snippet: snippetText,
          }}
        />
      );

      const toggleButton = screen.getByRole("button", { name: /show passage/i });
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId("source-snippet")).toBeNull();

      fireEvent.click(toggleButton);

      expect(toggleButton.getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByTestId("source-snippet").textContent).toBe(snippetText);

      fireEvent.click(toggleButton);
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId("source-snippet")).toBeNull();
    });

    it("an empty sources event renders no citation block", () => {
      const { container } = render(<SourceCard sources={[]} />);
      expect(container.firstChild).toBeNull();
      expect(screen.queryByTestId("citation-block")).toBeNull();
    });
  });

  describe("SourcePanel and StudioPanel", () => {
    it("SourcePanel renders truncated filename, tooltip, page count, chunk count, ready badge, and reset button", () => {
      const onReset = vi.fn();
      render(
        <SourcePanel
          filename="very-long-academic-paper-title-2026.pdf"
          pageCount={14}
          chunkCount={42}
          onReset={onReset}
          isReady={true}
        />
      );

      const titleEl = screen.getByTitle("very-long-academic-paper-title-2026.pdf");
      expect(titleEl).toBeDefined();
      expect(screen.getByText(/14 pages/i)).toBeDefined();
      expect(screen.getByText(/42 indexed/i)).toBeDefined();
      expect(screen.getByTestId("ready-badge")).toBeDefined();

      const resetBtn = screen.getByRole("button", {
        name: /upload another paper/i,
      });
      fireEvent.click(resetBtn);
      expect(onReset).toHaveBeenCalledTimes(1);
    });

    it("StudioPanel renders summary header and child SummaryView", () => {
      render(<StudioPanel summary={null} isLoading={false} error={null} />);
      expect(screen.getByText("Summary")).toBeDefined();
      expect(screen.getByText("No summary available")).toBeDefined();
    });

    it("renders ConvertLink with text 'Convert other files' when no paper is loaded", () => {
      render(<SourcePanel filename={null} onReset={vi.fn()} />);
      const link = screen.getByRole("link", { name: /convert other files/i });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toBe("https://www.ilovepdf.com");
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
      expect(
        screen.getByText(
          "Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to us."
        )
      ).toBeDefined();
    });

    it("does not render ConvertLink when a paper is loaded", () => {
      render(
        <SourcePanel
          filename="test.pdf"
          pageCount={5}
          chunkCount={10}
          onReset={vi.fn()}
        />
      );
      expect(
        screen.queryByRole("link", { name: /convert other files/i })
      ).toBeNull();
      expect(
        screen.queryByText(
          "Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to us."
        )
      ).toBeNull();
    });

    it("only one upload control is rendered before upload", () => {
      render(<SourcePanel filename={null} onReset={vi.fn()} />);

      // Single drop zone is rendered
      expect(
        screen.getByText("Click to upload or drag and drop")
      ).toBeDefined();
      expect(
        screen.getByText("PDF documents only (up to 20MB)")
      ).toBeDefined();
      expect(
        screen.getAllByRole("button", { name: /click to upload/i })
      ).toHaveLength(1);

      // The "+ Add PDF Document" button is removed
      expect(
        screen.queryByRole("button", { name: /add pdf document/i })
      ).toBeNull();

      // Only one file input is rendered in the DOM
      const fileInputs = document.querySelectorAll('input[type="file"]');
      expect(fileInputs).toHaveLength(1);
    });

    it("the drop zone accepts a file through click and through a drop event", async () => {
      const mockResult = {
        doc_hash: "d".repeat(64),
        filename: "test-paper.pdf",
        size_bytes: 1024,
        page_count: 4,
        chunk_count: 10,
      };
      vi.mocked(uploadPdf).mockResolvedValue(mockResult);

      // 1. Through click / file input change
      const onUploadedClick = vi.fn();
      const { unmount } = render(
        <UploadZone onUploaded={onUploadedClick} />
      );

      const dropZoneClick = screen.getByRole("button", {
        name: /click to upload/i,
      });
      fireEvent.click(dropZoneClick);

      const fileClick = new File(["click pdf"], "test-paper.pdf", {
        type: "application/pdf",
      });
      const inputClick = document.querySelector(
        'input[type="file"]'
      ) as HTMLInputElement;
      fireEvent.change(inputClick, { target: { files: [fileClick] } });

      await waitFor(() => {
        expect(onUploadedClick).toHaveBeenCalledWith(mockResult);
      });
      unmount();

      // 2. Through drop event
      const onUploadedDrop = vi.fn();
      render(<UploadZone onUploaded={onUploadedDrop} />);

      const dropZone = screen.getByRole("button", {
        name: /click to upload/i,
      });
      const fileDrop = new File(["drop pdf"], "test-paper.pdf", {
        type: "application/pdf",
      });

      fireEvent.dragOver(dropZone);
      fireEvent.drop(dropZone, {
        dataTransfer: { files: [fileDrop] },
      });

      await waitFor(() => {
        expect(onUploadedDrop).toHaveBeenCalledWith(mockResult);
      });
    });

    it("after upload, the compact row shows the filename and the 'Upload another paper' link", async () => {
      const onReset = vi.fn();
      const { rerender } = render(
        <SourcePanel filename={null} onReset={onReset} />
      );

      // Before upload: drop zone visible, compact row not visible
      expect(
        screen.getByText("Click to upload or drag and drop")
      ).toBeDefined();
      expect(screen.queryByTestId("compact-source-row")).toBeNull();

      // After upload: filename provided
      rerender(
        <SourcePanel filename="attention-mechanism.pdf" onReset={onReset} />
      );

      // Drop zone replaced by compact row
      expect(
        screen.queryByText("Click to upload or drag and drop")
      ).toBeNull();
      const compactRow = screen.getByTestId("compact-source-row");
      expect(compactRow).toBeDefined();
      expect(within(compactRow).getByText("attention-mechanism.pdf")).toBeDefined();

      const uploadAnotherLink = within(compactRow).getByRole("button", {
        name: /upload another paper/i,
      });
      expect(uploadAnotherLink).toBeDefined();

      // Clicking link triggers onReset to return to drop zone
      fireEvent.click(uploadAnotherLink);
      expect(onReset).toHaveBeenCalledTimes(1);

      // Returning drop zone when filename is cleared
      rerender(<SourcePanel filename={null} onReset={onReset} />);
      expect(
        screen.getByText("Click to upload or drag and drop")
      ).toBeDefined();
      expect(screen.queryByTestId("compact-source-row")).toBeNull();
    });
  });

  describe("ConvertLink", () => {
    it("renders the button with text 'Convert other files' and caption with exact wording", () => {
      render(<ConvertLink />);
      const btn = screen.getByRole("link", { name: /convert other files/i });
      expect(btn).toBeDefined();
      expect(screen.getByText("Convert other files")).toBeDefined();
      expect(
        screen.getByText(
          "Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to us."
        )
      ).toBeDefined();
    });

    it("has href https://www.ilovepdf.com, and target='_blank' and rel='noopener noreferrer'", () => {
      render(<ConvertLink />);
      const link = screen.getByRole("link", { name: /convert other files/i });
      expect(link.getAttribute("href")).toBe("https://www.ilovepdf.com");
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
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

    it("a grounded answer shows a collapsed 'Sources (N)' line, and expanding it shows the page and passage", async () => {
      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onToken("The core approach ");
        handlers.onToken("uses self-attention.");
        handlers.onSources([
          { page_number: 4, snippet: "Transformer models rely on self-attention." },
        ]);
        handlers.onDone();
      });

      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      );
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, {
        target: { value: "What is the architecture?" },
      });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByText("What is the architecture?")).toBeDefined();
        expect(
          screen.getByText("The core approach uses self-attention.")
        ).toBeDefined();
      });

      // Shows collapsed "Sources (1)" line by default
      const toggleButton = screen.getByRole("button", { name: "Sources (1)" });
      expect(toggleButton).toBeDefined();
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId("message-sources")).toBeNull();
      expect(screen.queryByText("Page 4")).toBeNull();
      expect(
        screen.queryByText("Transformer models rely on self-attention.")
      ).toBeNull();

      // Expanding the toggle sets aria-expanded to true and shows page and passage
      fireEvent.click(toggleButton);
      expect(toggleButton.getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByTestId("message-sources")).toBeDefined();
      expect(screen.getByText("Page 4")).toBeDefined();
      expect(
        screen.getByText("Transformer models rely on self-attention.")
      ).toBeDefined();

      expect(streamChat).toHaveBeenCalledTimes(1);
    });

    it("a chat answer with two sources shows collapsed Sources (2), and expanding it shows page numbers and passages", async () => {
      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onToken("Multi-head attention improves capacity.");
        handlers.onSources([
          { page_number: 3, snippet: "Self-attention operates across representation subspaces." },
          { page_number: 5, snippet: "Multi-head attention yields significant gains on translation." },
        ]);
        handlers.onDone();
      });

      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      );
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, { target: { value: "Explain multi-head attention" } });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(
          screen.getByText("Multi-head attention improves capacity.")
        ).toBeDefined();
      });

      // No inline citation buttons like [1] or [2]
      expect(screen.queryByRole("button", { name: "Citation [1]" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Citation [2]" })).toBeNull();

      // Collapsed Sources (2) line
      const toggle = screen.getByRole("button", { name: "Sources (2)" });
      expect(toggle.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId("message-sources")).toBeNull();

      // Expand toggle sets aria-expanded to true and reveals sources
      fireEvent.click(toggle);
      expect(toggle.getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByTestId("message-sources")).toBeDefined();
      expect(screen.getByText("Page 3")).toBeDefined();
      expect(
        screen.getByText("Self-attention operates across representation subspaces.")
      ).toBeDefined();
      expect(screen.getByText("Page 5")).toBeDefined();
      expect(
        screen.getByText("Multi-head attention yields significant gains on translation.")
      ).toBeDefined();
    });

    it("an answer with no sources shows no citation line", async () => {
      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onToken("I cannot answer this from the text.");
        handlers.onSources([]);
        handlers.onDone();
      });

      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      );
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, { target: { value: "Unrelated question" } });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(
          screen.getByText("I cannot answer this from the text.")
        ).toBeDefined();
      });

      expect(screen.queryByRole("button", { name: /sources/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /citation/i })).toBeNull();
      expect(screen.queryByTestId("citation-block")).toBeNull();
      expect(screen.queryByTestId("message-sources")).toBeNull();
    });

    it("whitespace-only input does not call streamChat", () => {
      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      );
      const sendButton = screen.getByRole("button", { name: /send message/i });

      fireEvent.change(textarea, { target: { value: "   \n\t  " } });
      fireEvent.click(sendButton);

      expect(streamChat).not.toHaveBeenCalled();
    });

    it("input over 2000 characters is rejected", () => {
      render(<ChatPanel docHash={docHash} />);

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      );
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

      const textarea = screen.getByPlaceholderText(
        /ask a question about this paper/i
      );
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
      expect(screen.getByText("Starting generated text...")).toBeDefined();
    });
  });

  describe("Workspace Responsive Layout (Home)", () => {
    const mockUploadResult = {
      doc_hash: "b".repeat(64),
      filename: "test-transformer.pdf",
      size_bytes: 4096,
      page_count: 8,
      chunk_count: 24,
    };

    const mockSummary: SummaryResponse = {
      header: {
        title: "Attention Mechanism Title",
        authors: "Authors List",
        abstract: "Abstract content",
      },
      title_authors_abstract: "Attention Mechanism Title",
      problem_statement: "Attention Problem",
      methodology: "Attention Methodology",
      key_results: "Attention Key Results",
      conclusion: "Attention Conclusion",
    };

    beforeEach(() => {
      vi.mocked(uploadPdf).mockResolvedValue(mockUploadResult);
      vi.mocked(getSummary).mockResolvedValue(mockSummary);
    });

    it("desktop layout renders all three panels when window.matchMedia reports a wide viewport", async () => {
      mockMatchMedia(true);

      render(<Home />);
      await screen.findByTestId("desktop-workspace");

      // Perform upload to transition to workspace
      const file = new File(["pdf content"], "test-transformer.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByTestId("desktop-workspace")).toBeDefined();
        expect(screen.getByTestId("desktop-source-panel")).toBeDefined();
        expect(screen.getByTestId("desktop-chat-panel")).toBeDefined();
        expect(screen.getByTestId("desktop-studio-panel")).toBeDefined();
      });

      // Mobile tab bar should not be in the desktop workspace container
      const desktopWorkspace = screen.getByTestId("desktop-workspace");
      expect(within(desktopWorkspace).queryByRole("tablist")).toBeNull();
    });

    it("mobile tab bar renders three tabs, and selecting Studio shows the summary", async () => {
      mockMatchMedia(false);

      render(<Home />);
      await screen.findByTestId("mobile-workspace");

      const file = new File(["pdf content"], "test-transformer.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByTestId("mobile-workspace")).toBeDefined();
      });

      const tabList = screen.getByRole("tablist", { name: "Workspace tabs" });
      expect(tabList).toBeDefined();

      const tabs = screen.getAllByRole("tab");
      expect(tabs).toHaveLength(3);
      expect(tabs[0].textContent).toContain("Source");
      expect(tabs[1].textContent).toContain("Chat");
      expect(tabs[2].textContent).toContain("Summary");

      // Chat is default tab after upload
      expect(tabs[1].getAttribute("aria-selected")).toBe("true");

      // Select Studio tab
      fireEvent.click(tabs[2]);
      expect(tabs[2].getAttribute("aria-selected")).toBe("true");

      // Summary should now be visible in Studio view scoped to mobile workspace
      await waitFor(() => {
        const mobileWorkspace = screen.getByTestId("mobile-workspace");
        expect(within(mobileWorkspace).getByTestId("studio-panel")).toBeDefined();
        expect(within(mobileWorkspace).getByText("Attention Mechanism Title")).toBeDefined();
      });
    });

    it("mobile tabs respond to keyboard arrow navigation", async () => {
      mockMatchMedia(false);

      render(<Home />);
      await screen.findByTestId("mobile-workspace");

      const file = new File(["pdf content"], "test-transformer.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByTestId("mobile-workspace")).toBeDefined();
      });

      const tabs = screen.getAllByRole("tab");
      // Initial tab is chat (index 1)
      expect(tabs[1].getAttribute("aria-selected")).toBe("true");

      // Press ArrowRight -> moves to Studio (index 2)
      fireEvent.keyDown(tabs[1], { key: "ArrowRight" });
      expect(tabs[2].getAttribute("aria-selected")).toBe("true");

      // Press ArrowRight again -> wraps around to Source (index 0)
      fireEvent.keyDown(tabs[2], { key: "ArrowRight" });
      expect(tabs[0].getAttribute("aria-selected")).toBe("true");

      // Press ArrowLeft -> wraps back to Studio (index 2)
      fireEvent.keyDown(tabs[0], { key: "ArrowLeft" });
      expect(tabs[2].getAttribute("aria-selected")).toBe("true");
    });

    it("switching from Chat to Summary and back keeps every message and citation, and switching documents clears previous messages", async () => {
      mockMatchMedia(false);

      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onToken("The core approach ");
        handlers.onToken("uses self-attention.");
        handlers.onSources([
          { page_number: 4, snippet: "Transformer models rely on self-attention." },
        ]);
        handlers.onDone();
      });

      render(<Home />);
      await screen.findByTestId("mobile-workspace");

      // Upload file
      const file = new File(["pdf content"], "test-transformer.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByTestId("mobile-workspace")).toBeDefined();
      });

      const mobileChatContainer = screen.getByTestId("mobile-chat-container");
      expect(mobileChatContainer.className).not.toContain("hidden");

      // Send a chat message in the mobile chat panel
      const textarea = within(mobileChatContainer).getByPlaceholderText(
        /ask a question about this paper/i
      );
      const sendButton = within(mobileChatContainer).getByRole("button", {
        name: /send message/i,
      });

      fireEvent.change(textarea, {
        target: { value: "What is the architecture?" },
      });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(
          within(mobileChatContainer).getByText("What is the architecture?")
        ).toBeDefined();
        expect(
          within(mobileChatContainer).getByText("The core approach uses self-attention.")
        ).toBeDefined();
        expect(
          within(mobileChatContainer).getByRole("button", { name: "Sources (1)" })
        ).toBeDefined();
      });

      // Expand citation
      const toggle = within(mobileChatContainer).getByRole("button", { name: "Sources (1)" });
      fireEvent.click(toggle);
      expect(within(mobileChatContainer).getByText("Page 4")).toBeDefined();
      expect(
        within(mobileChatContainer).getByText("Transformer models rely on self-attention.")
      ).toBeDefined();

      // Switch to Summary tab (tab index 2)
      const tabs = screen.getAllByRole("tab");
      fireEvent.click(tabs[2]);

      // Chat container should now be hidden via className, but remain mounted in DOM
      expect(screen.getByTestId("mobile-chat-container").className).toContain("hidden");
      expect(screen.getByTestId("mobile-studio-container").className).not.toContain("hidden");

      // Switch back to Chat tab (tab index 1)
      fireEvent.click(tabs[1]);
      expect(screen.getByTestId("mobile-chat-container").className).not.toContain("hidden");

      // Confirm every message and citation is still there
      expect(
        within(mobileChatContainer).getByText("What is the architecture?")
      ).toBeDefined();
      expect(
        within(mobileChatContainer).getByText("The core approach uses self-attention.")
      ).toBeDefined();
      expect(within(mobileChatContainer).getByText("Page 4")).toBeDefined();
      expect(
        within(mobileChatContainer).getByText("Transformer models rely on self-attention.")
      ).toBeDefined();

      // Switch to Source tab and click "Upload another paper" (Reset)
      fireEvent.click(tabs[0]);
      const resetBtn = within(screen.getByTestId("mobile-workspace")).getByRole("button", {
        name: /upload another paper/i,
      });
      fireEvent.click(resetBtn);

      // Confirm previous document's messages are cleared
      await waitFor(() => {
        expect(screen.queryByText("What is the architecture?")).toBeNull();
      });
    });

    it("an in-flight streamed answer keeps streaming while the chat panel is hidden", async () => {
      mockMatchMedia(false);

      let emitToken2: () => void = () => {};
      let finishStream: () => void = () => {};

      vi.mocked(streamChat).mockImplementation(async (_params, handlers) => {
        handlers.onToken("First token. ");
        emitToken2 = () => {
          handlers.onToken("Second in-flight token.");
          handlers.onSources([
            { page_number: 7, snippet: "In-flight citation snippet." },
          ]);
        };
        finishStream = () => {
          handlers.onDone();
        };
      });

      render(<Home />);
      await screen.findByTestId("mobile-workspace");

      // Upload file
      const file = new File(["pdf content"], "test-transformer.pdf", {
        type: "application/pdf",
      });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByTestId("mobile-workspace")).toBeDefined();
      });

      const mobileChatContainer = screen.getByTestId("mobile-chat-container");
      const textarea = within(mobileChatContainer).getByPlaceholderText(
        /ask a question about this paper/i
      );
      const sendButton = within(mobileChatContainer).getByRole("button", {
        name: /send message/i,
      });

      fireEvent.change(textarea, {
        target: { value: "Stream test question" },
      });
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(within(mobileChatContainer).getByText("First token.")).toBeDefined();
      });

      // Switch views to Summary while stream is in-flight
      const tabs = screen.getAllByRole("tab");
      fireEvent.click(tabs[2]); // Summary tab
      expect(screen.getByTestId("mobile-chat-container").className).toContain("hidden");

      // In-flight stream emits second token, sources, and completes while hidden
      emitToken2();
      finishStream();

      // Switch back to Chat view
      fireEvent.click(tabs[1]);
      expect(screen.getByTestId("mobile-chat-container").className).not.toContain("hidden");

      // Confirm streamed answer and citation were not dropped
      await waitFor(() => {
        expect(
          within(mobileChatContainer).getByText("First token. Second in-flight token.")
        ).toBeDefined();
        expect(
          within(mobileChatContainer).getByRole("button", { name: "Sources (1)" })
        ).toBeDefined();
      });
    });
  });

  describe("ThemeToggle", () => {
    beforeEach(() => {
      localStorage.clear();
      document.documentElement.classList.remove("dark");
    });

    it("toggles theme and updates document.documentElement class and localStorage", () => {
      render(<ThemeToggle />);

      const toggleBtn = screen.getByRole("button", {
        name: /switch to dark mode/i,
      });
      expect(toggleBtn).toBeDefined();

      fireEvent.click(toggleBtn);

      expect(document.documentElement.classList.contains("dark")).toBe(true);
      expect(localStorage.getItem("theme")).toBe("dark");

      const lightBtn = screen.getByRole("button", {
        name: /switch to light mode/i,
      });
      fireEvent.click(lightBtn);

      expect(document.documentElement.classList.contains("dark")).toBe(false);
      expect(localStorage.getItem("theme")).toBe("light");
    });
  });

  describe("ExportButton", () => {
    it("disabled with the visible reason when there is no summary", () => {
      render(<ExportButton docHash={null} messages={[]} />);
      const btn = screen.getByRole("button", { name: /export/i }) as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
      expect(screen.getByText("Upload a paper first.")).toBeDefined();
    });

    it("enabled when a summary docHash is present", () => {
      render(<ExportButton docHash={"a".repeat(64)} messages={[]} />);
      const btn = screen.getByRole("button", { name: /export/i }) as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
      expect(screen.queryByText("Upload a paper first.")).toBeNull();
    });

    it("clicking calls exportReport once with the document hash and at most 200 messages", async () => {
      vi.mocked(exportReport).mockResolvedValueOnce({
        blob: new Blob(["docx data"]),
        filename: "mitra-report-12345678.docx",
      });

      const manyMessages = Array.from({ length: 250 }, (_, i) => ({
        role: "user" as const,
        text: `Message ${i}`,
        sources: [],
      }));

      const docHash = "1234567890abcdef".repeat(4);
      render(<ExportButton docHash={docHash} messages={manyMessages} />);

      const btn = screen.getByRole("button", { name: /export/i });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(exportReport).toHaveBeenCalledTimes(1);
      });

      const [calledHash, calledMessages] = vi.mocked(exportReport).mock.calls[0];
      expect(calledHash).toBe(docHash);
      expect(calledMessages).toBeDefined();
      expect(calledMessages!.length).toBeLessThanOrEqual(200);
      expect(calledMessages!.length).toBe(200);
    });

    it("the download starts, using the filename from the response", async () => {
      const mockBlob = new Blob(["docx data"]);
      vi.mocked(exportReport).mockResolvedValueOnce({
        blob: mockBlob,
        filename: "mitra-report-abcdef12.docx",
      });

      const createObjectURLMock = vi.fn().mockReturnValue("blob:http://localhost/test-uuid");
      const revokeObjectURLMock = vi.fn();
      window.URL.createObjectURL = createObjectURLMock;
      window.URL.revokeObjectURL = revokeObjectURLMock;

      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click");

      render(<ExportButton docHash={"a".repeat(64)} messages={[]} />);
      const btn = screen.getByRole("button", { name: /export/i });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(createObjectURLMock).toHaveBeenCalledWith(mockBlob);
        expect(clickSpy).toHaveBeenCalledTimes(1);
        expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:http://localhost/test-uuid");
      });

      clickSpy.mockRestore();
    });

    it("a 404 shows its error text", async () => {
      vi.mocked(exportReport).mockRejectedValueOnce(
        new ApiError(404, "Document not found. Upload the PDF first.")
      );

      render(<ExportButton docHash={"a".repeat(64)} messages={[]} />);
      const btn = screen.getByRole("button", { name: /export/i });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(screen.getByText("Document not found. Upload the PDF first.")).toBeDefined();
      });
    });

    it("the button is disabled while the request runs", async () => {
      let resolvePromise!: (val: { blob: Blob; filename: string }) => void;
      const pendingPromise = new Promise<{ blob: Blob; filename: string }>((resolve) => {
        resolvePromise = resolve;
      });
      vi.mocked(exportReport).mockReturnValueOnce(pendingPromise);

      render(<ExportButton docHash={"a".repeat(64)} messages={[]} />);
      const btn = screen.getByRole("button", { name: /export/i });
      fireEvent.click(btn);

      await waitFor(() => {
        const preparingBtn = screen.getByRole("button", { name: /preparing file/i }) as HTMLButtonElement;
        expect(preparingBtn.disabled).toBe(true);
        expect(screen.getByText("Preparing file")).toBeDefined();
      });

      resolvePromise({ blob: new Blob(["done"]), filename: "mitra-report.docx" });
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /export/i })).toBeDefined();
      });
    });

    it("window.print is never called", async () => {
      window.print = vi.fn();
      vi.mocked(exportReport).mockResolvedValueOnce({
        blob: new Blob(["docx data"]),
        filename: "mitra-report-test.docx",
      });

      render(<ExportButton docHash={"a".repeat(64)} messages={[]} />);
      const btn = screen.getByRole("button", { name: /export/i });
      fireEvent.click(btn);

      await waitFor(() => {
        expect(exportReport).toHaveBeenCalledTimes(1);
      });

      expect(window.print).not.toHaveBeenCalled();
    });
  });

  describe("Authentication & Session Management", () => {
    it("sign-in tab is the default", () => {
      render(<AuthPanel onSuccess={vi.fn()} />);

      const signInTab = screen.getByRole("tab", { name: "Sign in" });
      const signUpTab = screen.getByRole("tab", { name: "Sign up" });

      expect(signInTab.getAttribute("aria-selected")).toBe("true");
      expect(signUpTab.getAttribute("aria-selected")).toBe("false");
      expect(screen.getByRole("button", { name: "Sign in" })).toBeDefined();
      expect(screen.queryByLabelText("Confirm password")).toBeNull();
    });

    it("mismatched passwords on sign-up show 'Passwords do not match.' without calling the API", async () => {
      const onSuccess = vi.fn();
      render(<AuthPanel onSuccess={onSuccess} />);

      // Switch to sign up tab
      fireEvent.click(screen.getByRole("tab", { name: "Sign up" }));
      expect(screen.getByLabelText("Confirm password")).toBeDefined();

      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByLabelText("Password"), {
        target: { value: "SecretPassword123" },
      });
      fireEvent.change(screen.getByLabelText("Confirm password"), {
        target: { value: "DifferentSecret456" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Create account" }));

      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toContain("Passwords do not match.");
      expect(signUp).not.toHaveBeenCalled();
      expect(onSuccess).not.toHaveBeenCalled();
    });

    it("a 401 from sign-in shows 'Email or password is incorrect.'", async () => {
      vi.mocked(signIn).mockRejectedValueOnce(
        new ApiError(401, "Email or password is incorrect.")
      );

      render(<AuthPanel onSuccess={vi.fn()} />);

      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "wrong@example.com" },
      });
      fireEvent.change(screen.getByLabelText("Password"), {
        target: { value: "WrongPass123" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toContain("Email or password is incorrect.");
    });

    it("a 429 shows the rate-limit message", async () => {
      vi.mocked(signIn).mockRejectedValueOnce(
        new ApiError(429, "Too many attempts. Try again in a few minutes.")
      );

      render(<AuthPanel onSuccess={vi.fn()} />);

      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "rate@example.com" },
      });
      fireEvent.change(screen.getByLabelText("Password"), {
        target: { value: "AnyPassword123" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toContain(
        "Too many attempts. Try again in a few minutes."
      );
    });

    it("focus moves to the first error on failure", async () => {
      render(<AuthPanel onSuccess={vi.fn()} />);

      fireEvent.click(screen.getByRole("tab", { name: "Sign up" }));
      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(screen.getByLabelText("Password"), {
        target: { value: "Secret123" },
      });
      fireEvent.change(screen.getByLabelText("Confirm password"), {
        target: { value: "Mismatch123" },
      });

      fireEvent.click(screen.getByRole("button", { name: "Create account" }));

      const alert = await screen.findByRole("alert");
      await waitFor(() => {
        expect(document.activeElement).toBe(alert);
      });
    });

    it("the submit button is disabled while the request runs", async () => {
      let resolvePromise: (value: { id: string; email: string }) => void;
      const pendingPromise = new Promise<{ id: string; email: string }>(
        (resolve) => {
          resolvePromise = resolve;
        }
      );
      vi.mocked(signIn).mockReturnValueOnce(pendingPromise);

      render(<AuthPanel onSuccess={vi.fn()} />);

      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "wait@example.com" },
      });
      fireEvent.change(screen.getByLabelText("Password"), {
        target: { value: "Pass123456" },
      });

      const submitBtn = screen.getByRole("button", { name: "Sign in" }) as HTMLButtonElement;
      fireEvent.click(submitBtn);

      await waitFor(() => {
        const btn = screen.getByRole("button", { name: /signing in/i }) as HTMLButtonElement;
        expect(btn.disabled).toBe(true);
      });

      resolvePromise!({ id: "user-1", email: "wait@example.com" });
    });

    it("on load with a valid session, the workspace shows; without one, the sign-in page shows", async () => {
      // 1. Valid session
      vi.mocked(getMe).mockResolvedValueOnce({
        id: "user-valid",
        email: "valid@example.com",
      });

      const { unmount } = render(<Home />);
      const desktopWorkspace = await screen.findByTestId("desktop-workspace");
      expect(desktopWorkspace).toBeDefined();
      expect(screen.queryByTestId("auth-page")).toBeNull();
      unmount();

      // 2. Without valid session (401)
      vi.mocked(getMe).mockRejectedValueOnce(
        new ApiError(401, "Not authenticated")
      );

      render(<Home />);
      const authPage = await screen.findByTestId("auth-page");
      expect(authPage).toBeDefined();
      expect(screen.queryByTestId("desktop-workspace")).toBeNull();
    });

    it("sign-out returns to the sign-in page via avatar menu", async () => {
      vi.mocked(getMe).mockResolvedValueOnce({
        id: "user-1",
        email: "logged_in@example.com",
      });
      vi.mocked(signOut).mockResolvedValueOnce({ status: "ok" });

      render(<Home />);
      expect(await screen.findByTestId("desktop-workspace")).toBeDefined();

      const avatar = await screen.findByTestId("profile-avatar");
      fireEvent.click(avatar);

      const menuEmail = await screen.findByTestId("profile-menu-email");
      expect(menuEmail.textContent).toBe("logged_in@example.com");

      const signOutBtn = await screen.findByTestId("menu-item-sign-out");
      fireEvent.click(signOutBtn);

      await waitFor(() => {
        expect(screen.getByTestId("auth-page")).toBeDefined();
      });
      expect(screen.queryByTestId("desktop-workspace")).toBeNull();
    });

    it("top bar has no standalone Sign out button or email display", async () => {
      vi.mocked(getMe).mockResolvedValueOnce({
        id: "user-1",
        email: "logged_in@example.com",
      });

      render(<Home />);
      expect(await screen.findByTestId("desktop-workspace")).toBeDefined();

      expect(screen.queryByTestId("sign-out-btn")).toBeNull();
      expect(screen.queryByTestId("user-email-display")).toBeNull();
      expect(screen.queryByTestId("user-session-controls")).toBeNull();
    });
  });

  describe("Profile and Password Change", () => {
    it("initials come from the name when set, otherwise from the email", async () => {
      // 1. When display_name is set
      const { unmount } = render(
        <ProfileMenu
          user={{
            id: "user-1",
            email: "ada@example.com",
            display_name: "Ada Lovelace",
          }}
        />
      );

      const avatar = screen.getByTestId("profile-avatar");
      await waitFor(() => {
        expect(avatar.textContent).toBe("AL");
      });
      unmount();

      // 2. When display_name is null/unset
      render(
        <ProfileMenu
          user={{
            id: "user-2",
            email: "grace@example.com",
            display_name: null,
          }}
        />
      );

      const avatarEmail = screen.getByTestId("profile-avatar");
      await waitFor(() => {
        expect(avatarEmail.textContent).toBe("GR");
      });
    });

    it("saving trims and calls the API once", async () => {
      const onSaveMock = vi.fn().mockResolvedValue(undefined);
      render(<ProfileForm initialDisplayName="" onSave={onSaveMock} />);

      const input = screen.getByTestId("profile-name-input");
      fireEvent.change(input, { target: { value: "   Grace Hopper   " } });

      const saveBtn = screen.getByTestId("profile-save-btn");
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(onSaveMock).toHaveBeenCalledTimes(1);
        expect(onSaveMock).toHaveBeenCalledWith("Grace Hopper");
      });
    });

    it("a name over 60 characters shows its error without calling the API", async () => {
      const onSaveMock = vi.fn();
      render(<ProfileForm initialDisplayName="" onSave={onSaveMock} />);

      const input = screen.getByTestId("profile-name-input");
      const longName = "a".repeat(61);
      fireEvent.change(input, { target: { value: longName } });

      const saveBtn = screen.getByTestId("profile-save-btn");
      fireEvent.click(saveBtn);

      expect(onSaveMock).not.toHaveBeenCalled();
      const errorMsg = await screen.findByTestId("profile-form-error");
      expect(errorMsg.textContent).toBe(
        "Display name must be 60 characters or fewer."
      );
    });

    it("the menu opens, closes on Escape, and returns focus", async () => {
      render(
        <ProfileMenu
          user={{
            id: "user-1",
            email: "test@example.com",
            display_name: "Test User",
          }}
        />
      );

      const avatar = screen.getByTestId("profile-avatar");
      expect(screen.queryByRole("menu")).toBeNull();

      // Open menu
      fireEvent.click(avatar);
      const menu = await screen.findByRole("menu");
      expect(menu).toBeDefined();
      expect(screen.getByTestId("menu-item-edit-profile")).toBeDefined();
      expect(screen.getByTestId("menu-item-change-password")).toBeDefined();
      expect(screen.getByTestId("menu-item-sign-out")).toBeDefined();

      // Press Escape to close
      fireEvent.keyDown(menu, { key: "Escape" });
      expect(screen.queryByRole("menu")).toBeNull();
      expect(document.activeElement).toBe(avatar);
    });

    it("mismatched new passwords show their error without calling the API", async () => {
      render(<ChangePasswordForm />);

      fireEvent.change(screen.getByTestId("current-password-input"), {
        target: { value: "oldpassword123" },
      });
      fireEvent.change(screen.getByTestId("new-password-input"), {
        target: { value: "newpassword456" },
      });
      fireEvent.change(screen.getByTestId("confirm-password-input"), {
        target: { value: "mismatchpassword" },
      });

      fireEvent.click(screen.getByTestId("change-password-submit-btn"));

      expect(changePassword).not.toHaveBeenCalled();
      const errorMsg = await screen.findByTestId("confirm-password-error");
      expect(errorMsg.textContent).toBe("Passwords do not match.");
    });

    it("a 401 shows “Current password is incorrect.”", async () => {
      vi.mocked(changePassword).mockRejectedValueOnce(
        new ApiError(401, "Current password is incorrect.")
      );

      render(<ChangePasswordForm />);

      fireEvent.change(screen.getByTestId("current-password-input"), {
        target: { value: "wrongpwd123" },
      });
      fireEvent.change(screen.getByTestId("new-password-input"), {
        target: { value: "newpassword456" },
      });
      fireEvent.change(screen.getByTestId("confirm-password-input"), {
        target: { value: "newpassword456" },
      });

      fireEvent.click(screen.getByTestId("change-password-submit-btn"));

      const errorMsg = await screen.findByTestId("current-password-error");
      expect(errorMsg.textContent).toBe("Current password is incorrect.");
    });

    it("success shows “Password changed. Other devices have been signed out.”", async () => {
      vi.mocked(changePassword).mockResolvedValueOnce({ status: "ok" });

      render(<ChangePasswordForm />);

      fireEvent.change(screen.getByTestId("current-password-input"), {
        target: { value: "correctpwd123" },
      });
      fireEvent.change(screen.getByTestId("new-password-input"), {
        target: { value: "newpassword456" },
      });
      fireEvent.change(screen.getByTestId("confirm-password-input"), {
        target: { value: "newpassword456" },
      });

      fireEvent.click(screen.getByTestId("change-password-submit-btn"));

      const successMsg = await screen.findByTestId("change-password-success");
      expect(successMsg.textContent).toBe(
        "Password changed. Other devices have been signed out."
      );
    });
  });

  describe("CredibilityCard", () => {
    it("renders nothing when docHash is not provided (empty state)", () => {
      const { container } = render(<CredibilityCard docHash={null} />);
      expect(container.firstChild).toBeNull();
    });

    it("renders processing state while analysis is running", async () => {
      vi.mocked(getDocumentCredibility).mockResolvedValueOnce({
        status: "processing",
        external_check: "skipped",
        score: 0,
        badge_label: "Analyzing signals...",
        badge_variant: "neutral",
        signals: {
          venue_points: 0,
          citation_points: 0,
          reference_points: 0,
          affiliation_points: 0,
          structure_points: 0,
          bonus_points: 0,
          estimated_references: 0,
          recorded_citations: 0,
          has_doi: false,
          has_academic_affiliation: false,
          structure_sections_found: 0,
          open_artifacts_detected: false,
        },
        disclaimer: "Reporting signals score.",
      });

      render(<CredibilityCard docHash="test-doc-hash" />);

      expect(
        screen.getByTestId("credibility-card-processing")
      ).toBeDefined();
      expect(
        screen.getByText("Analyzing publication signals...")
      ).toBeDefined();
    });

    it("renders completed 5-row checklist, badge, bonus, and secondary score", async () => {
      const completedData: CredibilityResponse = {
        status: "completed",
        external_check: "matched",
        score: 82,
        badge_label: "Venue Matched in Crossref",
        badge_variant: "success",
        signals: {
          venue_points: 35,
          citation_points: 20,
          reference_points: 10,
          affiliation_points: 10,
          structure_points: 7,
          bonus_points: 5,
          matched_venue: "CVPR",
          estimated_references: 15,
          recorded_citations: 25,
          publication_year: 2021,
          has_doi: true,
          doi: "10.1109/cvpr.2021.12345",
          has_academic_affiliation: true,
          structure_sections_found: 3,
          open_artifacts_detected: true,
        },
        disclaimer:
          "Reporting signals score. Does not verify experimental correctness or research quality.",
      };

      vi.mocked(getDocumentCredibility).mockResolvedValueOnce(completedData);

      render(<CredibilityCard docHash="test-doc-hash" />);

      await waitFor(() => {
        expect(screen.getByTestId("credibility-card")).toBeDefined();
      });

      // Badge
      const badge = screen.getByTestId("credibility-badge");
      expect(badge.textContent).toBe("Venue Matched in Crossref");

      // 5-Row checklist items
      expect(screen.getByText("CVPR")).toBeDefined();
      expect(screen.getByText("15 detected")).toBeDefined();
      expect(screen.getByText("25 recorded")).toBeDefined();
      expect(screen.getByText("Academic (.edu / ac)")).toBeDefined();
      expect(screen.getByText("3/4 sections")).toBeDefined();

      // Tooltip for references < 20
      expect(screen.getByTestId("ref-estimate-tooltip")).toBeDefined();

      // Bonus row
      expect(screen.getByTestId("credibility-bonus")).toBeDefined();
      expect(
        screen.getByText("+5 bonus: Public code/data repo detected")
      ).toBeDefined();

      // Secondary figure
      expect(screen.getByTestId("credibility-score-figure").textContent).toBe(
        "82/100"
      );
    });

    it("renders 'Analysis unavailable' when polling times out (> 30s)", async () => {
      vi.useFakeTimers();

      vi.mocked(getDocumentCredibility).mockResolvedValue({
        status: "processing",
        external_check: "skipped",
        score: 0,
        badge_label: "Analyzing signals...",
        badge_variant: "neutral",
        signals: {
          venue_points: 0,
          citation_points: 0,
          reference_points: 0,
          affiliation_points: 0,
          structure_points: 0,
          bonus_points: 0,
          estimated_references: 0,
          recorded_citations: 0,
          has_doi: false,
          has_academic_affiliation: false,
          structure_sections_found: 0,
          open_artifacts_detected: false,
        },
        disclaimer: "Reporting signals score.",
      });

      render(<CredibilityCard docHash="test-doc-hash" />);

      // Fast-forward past 30 seconds
      await act(async () => {
        await vi.advanceTimersByTimeAsync(31000);
      });

      expect(screen.getByTestId("credibility-card-error")).toBeDefined();
      expect(screen.getByText("Analysis unavailable")).toBeDefined();

      vi.useRealTimers();
    });

    it("renders reference count ('14 detected') and section count ('3/4 sections') completely without clipping", async () => {
      const formattingData: CredibilityResponse = {
        status: "completed",
        external_check: "matched",
        score: 75,
        badge_label: "Venue Matched in Crossref",
        badge_variant: "success",
        signals: {
          venue_points: 35,
          citation_points: 15,
          reference_points: 10,
          affiliation_points: 10,
          structure_points: 7,
          bonus_points: 0,
          matched_venue: "IEEE Trans. Big Data",
          estimated_references: 14,
          recorded_citations: 12,
          publication_year: 2022,
          has_doi: true,
          doi: "10.1109/TBD.2022.12345",
          has_academic_affiliation: true,
          structure_sections_found: 3,
          open_artifacts_detected: false,
        },
        disclaimer: "Reporting signals score.",
      };

      vi.mocked(getDocumentCredibility).mockResolvedValueOnce(formattingData);

      render(<CredibilityCard docHash="test-format-doc" />);

      await waitFor(() => {
        expect(screen.getByTestId("credibility-card")).toBeDefined();
      });

      const refCountEl = screen.getByTestId("ref-count-text");
      expect(refCountEl.textContent).toBe("14 detected");
      expect(refCountEl.className).toContain("whitespace-nowrap");

      const sectionCountEl = screen.getByTestId("section-count-text");
      expect(sectionCountEl.textContent).toBe("3/4 sections");
      expect(sectionCountEl.className).toContain("whitespace-nowrap");
    });

    it("renders '0 detected' and '0/4 sections' without blank clipping when counts are 0 or undefined", async () => {
      const zeroData: CredibilityResponse = {
        status: "completed",
        external_check: "not_matched",
        score: 42,
        badge_label: "Unindexed Draft",
        badge_variant: "neutral",
        signals: {
          reference_count_estimated: 0,
          citation_count: 0,
          author_academic_affiliation: false,
          structure_sections_found: 0,
        },
        disclaimer: "Reporting signals score.",
      };

      vi.mocked(getDocumentCredibility).mockResolvedValueOnce(zeroData);

      render(<CredibilityCard docHash="test-zero-doc" />);

      await waitFor(() => {
        expect(screen.getByTestId("credibility-card")).toBeDefined();
      });

      const badge = screen.getByTestId("credibility-badge");
      expect(badge.textContent).toBe("Unindexed Draft");

      const refCountEl = screen.getByTestId("ref-count-text");
      expect(refCountEl.textContent).toBe("0 detected");

      const sectionCountEl = screen.getByTestId("section-count-text");
      expect(sectionCountEl.textContent).toBe("0/4 sections");
    });

    it("renders 'Indexed in OpenAlex' badge when score >= 75", async () => {
      const openAlexData: CredibilityResponse = {
        status: "completed",
        external_check: "matched",
        score: 85,
        badge_label: "Indexed in OpenAlex",
        badge_variant: "success",
        signals: {
          reference_count_estimated: 25,
          citation_count: 50,
          author_academic_affiliation: true,
          structure_sections_found: 4,
          matched_venue: "IEEE Transactions on Pattern Analysis and Machine Intelligence",
          venue_points: 35,
          citation_points: 25,
          reference_points: 20,
          affiliation_points: 10,
          structure_points: 10,
        },
        disclaimer: "Reporting signals score.",
      };

      vi.mocked(getDocumentCredibility).mockResolvedValueOnce(openAlexData);

      render(<CredibilityCard docHash="test-openalex-doc" />);

      await waitFor(() => {
        expect(screen.getByTestId("credibility-card")).toBeDefined();
      });

      const badge = screen.getByTestId("credibility-badge");
      expect(badge.textContent).toBe("Indexed in OpenAlex");
      expect(badge.className).toContain("text-emerald-700");
    });
  });

  describe("HelpButton and HelpPanel", () => {
    function HelpTestWrapper() {
      const [isOpen, setIsOpen] = React.useState(false);
      const btnRef = React.useRef<HTMLButtonElement | null>(null);

      return (
        <div>
          <HelpButton
            ref={btnRef}
            isOpen={isOpen}
            onClick={() => setIsOpen((prev) => !prev)}
          />
          <HelpPanel
            isOpen={isOpen}
            onClose={() => setIsOpen(false)}
            triggerRef={btnRef}
          />
        </div>
      );
    }

    it("renders HelpButton with accessible name 'Help' and dynamic aria-expanded", () => {
      render(<HelpTestWrapper />);
      const btn = screen.getByRole("button", { name: "Help" });
      expect(btn).toBeDefined();
      expect(btn.getAttribute("aria-expanded")).toBe("false");

      fireEvent.click(btn);
      expect(btn.getAttribute("aria-expanded")).toBe("true");

      const closeBtn = screen.getByTestId("help-panel-close-btn");
      fireEvent.click(closeBtn);
      expect(btn.getAttribute("aria-expanded")).toBe("false");
    });

    it("renders HelpPanel with accessible dialog semantics, aria-modal='true', and title 'How to use this'", () => {
      render(<HelpTestWrapper />);
      const helpBtn = screen.getByRole("button", { name: "Help" });
      fireEvent.click(helpBtn);

      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeDefined();
      expect(dialog.getAttribute("aria-modal")).toBe("true");
      expect(dialog.getAttribute("aria-labelledby")).toBe("help-panel-title");

      const title = screen.getByRole("heading", { name: "How to use this" });
      expect(title).toBeDefined();
      expect(title.id).toBe("help-panel-title");
    });

    it("renders all seven section headings in exact sequence", () => {
      render(<HelpTestWrapper />);
      fireEvent.click(screen.getByRole("button", { name: "Help" }));

      const expectedHeadings = [
        "Getting started",
        "Reading the summary",
        "Asking questions",
        "Citations",
        "Exporting",
        "Account",
        "Limits",
      ];

      const headings = screen
        .getAllByRole("heading")
        .filter((h) => h.id !== "help-panel-title")
        .map((h) => h.textContent?.trim());

      expect(headings).toEqual(expectedHeadings);
    });

    it("contains exact required substrings: '20 MB', '2000 characters', 'one paper'", () => {
      render(<HelpTestWrapper />);
      fireEvent.click(screen.getByRole("button", { name: "Help" }));

      const dialog = screen.getByRole("dialog");
      const dialogText = dialog.textContent || "";

      expect(dialogText).toContain("20 MB");
      expect(dialogText).toContain("2000 characters");
      expect(dialogText).toContain("one paper");
    });

    it("closes on Escape key press and restores focus to Help button", async () => {
      render(<HelpTestWrapper />);
      const helpBtn = screen.getByRole("button", { name: "Help" });
      helpBtn.focus();
      expect(document.activeElement).toBe(helpBtn);

      fireEvent.click(helpBtn);
      expect(screen.getByRole("dialog")).toBeDefined();

      fireEvent.keyDown(window, { key: "Escape", code: "Escape" });

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(document.activeElement).toBe(helpBtn);
    });

    it("closes on backdrop click and restores focus to Help button", async () => {
      render(<HelpTestWrapper />);
      const helpBtn = screen.getByRole("button", { name: "Help" });
      helpBtn.focus();

      fireEvent.click(helpBtn);
      expect(screen.getByRole("dialog")).toBeDefined();

      const backdrop = screen.getByTestId("help-panel-backdrop");
      fireEvent.click(backdrop);

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(document.activeElement).toBe(helpBtn);
    });

    it("traps focus with Tab and Shift+Tab while open", () => {
      render(<HelpTestWrapper />);
      const helpBtn = screen.getByRole("button", { name: "Help" });
      fireEvent.click(helpBtn);

      const dialog = screen.getByRole("dialog");
      const closeBtn = screen.getByTestId("help-panel-close-btn");

      // With only closeBtn focusable in this dialog, Tab wraps to closeBtn
      closeBtn.focus();
      expect(document.activeElement).toBe(closeBtn);

      fireEvent.keyDown(dialog, { key: "Tab" });
      expect(document.activeElement).toBe(closeBtn);

      fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
      expect(document.activeElement).toBe(closeBtn);
    });

    it("uses pure responsive Tailwind classes for bottom sheet and desktop drawer", () => {
      render(<HelpTestWrapper />);
      fireEvent.click(screen.getByRole("button", { name: "Help" }));

      const dialog = screen.getByRole("dialog");
      const className = dialog.className;

      // Bottom sheet classes for mobile
      expect(className).toContain("bottom-0");
      expect(className).toContain("inset-x-0");
      expect(className).toContain("rounded-t-2xl");

      // Desktop drawer classes for lg:
      expect(className).toContain("lg:inset-y-0");
      expect(className).toContain("lg:right-0");
      expect(className).toContain("lg:w-[440px]");
      expect(className).toContain("lg:rounded-none");
    });
  });

  describe("PdfViewerDrawer and ViewPdfButton", () => {
    function PdfViewerHarness({ initialBlob = "blob:http://localhost:3000/sample-paper-uuid" }: { initialBlob?: string | null }) {
      const [isOpen, setIsOpen] = React.useState(false);
      const [blobUrl] = React.useState<string | null>(initialBlob);
      const btnRef = React.useRef<HTMLButtonElement | null>(null);

      return (
        <div>
          <ViewPdfButton
            ref={btnRef}
            hasDocument={Boolean(blobUrl)}
            isOpen={isOpen}
            onClick={() => setIsOpen((prev) => !prev)}
          />
          <PdfViewerDrawer
            isOpen={isOpen}
            onClose={() => setIsOpen(false)}
            blobUrl={blobUrl}
            filename="sample-paper.pdf"
            triggerRef={btnRef}
          />
        </div>
      );
    }

    it("ViewPdfButton is hidden with no paper and visible with a paper", () => {
      // 1. With no paper loaded: button is not rendered
      const { unmount } = render(
        <ViewPdfButton hasDocument={false} onClick={vi.fn()} />
      );
      expect(screen.queryByRole("button", { name: "View PDF" })).toBeNull();
      expect(screen.queryByTestId("view-pdf-button")).toBeNull();
      unmount();

      // 2. With paper loaded: button is rendered with accessible name and tooltip
      render(<ViewPdfButton hasDocument={true} onClick={vi.fn()} />);
      const btn = screen.getByRole("button", { name: "View PDF" });
      expect(btn).toBeDefined();
      expect(btn.getAttribute("title")).toBe("View PDF");
      expect(btn.getAttribute("aria-label")).toBe("View PDF");
    });

    it("The drawer has role=\"dialog\", aria-modal=\"true\", and the correct aria-label", () => {
      render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={vi.fn()}
          blobUrl="blob:http://localhost:3000/test.pdf"
          filename="test.pdf"
        />
      );

      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeDefined();
      expect(dialog.getAttribute("aria-modal")).toBe("true");
      expect(dialog.getAttribute("aria-label")).toBe("Original PDF Document");
    });

    it("Escape, the close button, and a backdrop click each close the drawer", async () => {
      // 1. Close button
      const onCloseBtn = vi.fn();
      const { unmount: unmount1 } = render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={onCloseBtn}
          blobUrl="blob:http://localhost:3000/test.pdf"
        />
      );
      fireEvent.click(screen.getByTestId("pdf-viewer-close-btn"));
      expect(onCloseBtn).toHaveBeenCalledTimes(1);
      unmount1();

      // 2. Backdrop click
      const onCloseBackdrop = vi.fn();
      const { unmount: unmount2 } = render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={onCloseBackdrop}
          blobUrl="blob:http://localhost:3000/test.pdf"
        />
      );
      fireEvent.click(screen.getByTestId("pdf-viewer-backdrop"));
      expect(onCloseBackdrop).toHaveBeenCalledTimes(1);
      unmount2();

      // 3. Escape key
      const onCloseEscape = vi.fn();
      render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={onCloseEscape}
          blobUrl="blob:http://localhost:3000/test.pdf"
        />
      );
      fireEvent.keyDown(window, { key: "Escape", code: "Escape" });
      expect(onCloseEscape).toHaveBeenCalledTimes(1);
    });

    it("Focus returns to the View PDF button on close", async () => {
      render(<PdfViewerHarness />);

      const viewBtn = screen.getByRole("button", { name: "View PDF" });
      viewBtn.focus();
      expect(document.activeElement).toBe(viewBtn);

      // Open drawer
      fireEvent.click(viewBtn);
      expect(screen.getByRole("dialog")).toBeDefined();

      // Close drawer via close button
      const closeBtn = screen.getByTestId("pdf-viewer-close-btn");
      fireEvent.click(closeBtn);

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
      expect(document.activeElement).toBe(viewBtn);
    });

    it("Mount, unmount, and remount keeps a valid URL and doesn’t show a revoked blob", () => {
      const revokeSpy = vi.spyOn(URL, "revokeObjectURL");
      const testBlobUrl = "blob:http://localhost:3000/react-strict-mode-blob-uuid";

      // Initial Mount
      const { unmount } = render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={vi.fn()}
          blobUrl={testBlobUrl}
        />
      );

      // Unmount (as happens under React Strict Mode or drawer toggle)
      unmount();

      // URL must NOT be revoked on simple unmount
      expect(revokeSpy).not.toHaveBeenCalled();

      // Remount
      render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={vi.fn()}
          blobUrl={testBlobUrl}
        />
      );

      const objectEl = screen.getByRole("dialog").querySelector("object");
      expect(objectEl).toBeDefined();
      expect(objectEl?.getAttribute("data")).toBe(testBlobUrl);
      expect(revokeSpy).not.toHaveBeenCalled();

      revokeSpy.mockRestore();
    });

    it("The fallback text and “Open in new tab” link are present in the DOM", () => {
      const testBlobUrl = "blob:http://localhost:3000/document-fallback.pdf";
      render(
        <PdfViewerDrawer
          isOpen={true}
          onClose={vi.fn()}
          blobUrl={testBlobUrl}
        />
      );

      // Fallback text
      expect(
        screen.getByText("Your browser can’t show this PDF inline.")
      ).toBeDefined();

      // "Open in new tab" link inside the fallback
      const link = screen.getByRole("link", { name: /open in new tab/i });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toBe(testBlobUrl);
      expect(link.getAttribute("target")).toBe("_blank");

      // Privacy statement
      expect(
        screen.getByText(
          "The PDF is shown from memory in your browser. The server keeps only the extracted text and index, as before."
        )
      ).toBeDefined();
    });
  });
});
