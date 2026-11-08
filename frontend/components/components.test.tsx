import React from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
  within,
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
import { ProfileMenu } from "./ProfileMenu";
import { ProfileForm } from "./ProfileForm";
import { ChangePasswordForm } from "./ChangePasswordForm";
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
  });

  describe("SummaryView", () => {
    const mockSummary: SummaryResponse = {
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

      // Section 1 is expanded by default
      expect(
        screen.getByText("Attention Is All You Need by Vaswani et al.")
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

      expect(writeTextMock).toHaveBeenCalledWith(
        mockSummary.title_authors_abstract
      );

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
          "Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to Mitra."
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
          "Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to Mitra."
        )
      ).toBeNull();
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
          "Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to Mitra."
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
        expect(screen.getByTestId("message-sources")).toBeDefined();
        expect(screen.getByText("Page 4")).toBeDefined();
      });

      expect(streamChat).toHaveBeenCalledTimes(1);
    });

    it("a chat answer with two sources shows markers [1] and [2], and clicking [2] shows its passage with its page number", async () => {
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
        expect(screen.getByRole("button", { name: "Citation [1]" })).toBeDefined();
        expect(screen.getByRole("button", { name: "Citation [2]" })).toBeDefined();
      });

      // Source 2 passage is initially not expanded
      expect(
        screen.queryByText(/Multi-head attention yields significant gains on translation./)
      ).toBeNull();

      // Click citation marker [2]
      const marker2 = screen.getByRole("button", { name: "Citation [2]" });
      fireEvent.click(marker2);

      // Verifies passage appears with its page number
      await waitFor(() => {
        expect(screen.getByText("Passage from Page 5:")).toBeDefined();
        expect(
          screen.getByText("Multi-head attention yields significant gains on translation.")
        ).toBeDefined();
      });
    });

    it("a message with no sources shows no markers", async () => {
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

      expect(screen.queryByRole("button", { name: /Citation \[/i })).toBeNull();
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
});
