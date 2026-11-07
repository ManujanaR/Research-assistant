import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  ChatMessage,
  ChatSource,
  getSummary,
  streamChat,
  StreamChatHandlers,
  uploadPdf,
} from "./api";
import { parseSSE } from "./sse";

function createMockStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function mockResponse({
  status = 200,
  ok = true,
  json,
  body = null,
  statusText = "OK",
}: {
  status?: number;
  ok?: boolean;
  json?: unknown;
  body?: ReadableStream<Uint8Array> | null;
  statusText?: string;
}): Response {
  return {
    status,
    ok,
    statusText,
    json: async () => json,
    body,
  } as unknown as Response;
}

describe("frontend api client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe("uploadPdf", () => {
    it("returns the parsed UploadResponse on 200", async () => {
      const mockPayload = {
        doc_hash: "a".repeat(64),
        filename: "paper.pdf",
        size_bytes: 1024,
        page_count: 3,
        chunk_count: 7,
      };

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 200,
          ok: true,
          json: mockPayload,
        })
      );

      const file = new File(["dummy pdf content"], "paper.pdf", {
        type: "application/pdf",
      });
      const result = await uploadPdf(file);

      expect(result).toEqual(mockPayload);
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it("throws ApiError with status 415 and the backend's detail on a 415 response", async () => {
      const detail = "Invalid file type: only application/pdf is accepted.";
      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 415,
          ok: false,
          json: { detail },
        })
      );

      const file = new File(["dummy"], "test.txt", { type: "text/plain" });
      await expect(uploadPdf(file)).rejects.toThrow(ApiError);

      try {
        await uploadPdf(file);
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(415);
        expect(apiErr.detail).toBe(detail);
      }
    });

    it("throws ApiError with status 413 and the size message", async () => {
      const detail = "File exceeds maximum allowed size of 20MB.";
      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 413,
          ok: false,
          json: { detail },
        })
      );

      const file = new File(["huge"], "big.pdf", { type: "application/pdf" });
      try {
        await uploadPdf(file);
        expect.fail("Expected uploadPdf to throw");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(413);
        expect(apiErr.detail).toBe(detail);
      }
    });

    it("throws ApiError with status 422 and a readable string when detail is an array", async () => {
      const detailArray = [
        { loc: ["body", "file"], msg: "Field required", type: "missing" },
        { loc: ["body", "other"], msg: "Invalid parameter", type: "value_error" },
      ];

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 422,
          ok: false,
          json: { detail: detailArray },
        })
      );

      const file = new File(["data"], "test.pdf", { type: "application/pdf" });
      try {
        await uploadPdf(file);
        expect.fail("Expected uploadPdf to throw");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(422);
        expect(apiErr.detail).toBe("Field required; Invalid parameter");
        expect(apiErr.detail).not.toContain("{");
      }
    });

    it("throws ApiError with status 0 when fetch rejects", async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error("Connection refused"));

      const file = new File(["data"], "test.pdf", { type: "application/pdf" });
      try {
        await uploadPdf(file);
        expect.fail("Expected uploadPdf to throw");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(0);
        expect(apiErr.detail).toBe("Connection refused");
      }
    });
  });

  describe("getSummary", () => {
    it("returns the five fields in order", async () => {
      const summaryPayload = {
        title_authors_abstract: "Title and Abstract",
        problem_statement: "Problem statement here",
        methodology: "Methodology details",
        key_results: "Results and findings",
        conclusion: "Conclusions drawn",
      };

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 200,
          ok: true,
          json: summaryPayload,
        })
      );

      const result = await getSummary("b".repeat(64));

      expect(Object.keys(result)).toEqual([
        "title_authors_abstract",
        "problem_statement",
        "methodology",
        "key_results",
        "conclusion",
      ]);
      expect(result).toEqual(summaryPayload);
    });

    it("throws ApiError with status 404 and 502 detail messages", async () => {
      // 404 Test
      global.fetch = vi.fn().mockResolvedValueOnce(
        mockResponse({
          status: 404,
          ok: false,
          json: { detail: "Document text not found for doc_hash." },
        })
      );

      try {
        await getSummary("c".repeat(64));
        expect.fail("Expected getSummary to throw 404");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(404);
        expect(apiErr.detail).toBe("Document text not found for doc_hash.");
      }

      // 502 Test
      global.fetch = vi.fn().mockResolvedValueOnce(
        mockResponse({
          status: 502,
          ok: false,
          json: { detail: "Failed to generate structured summary from paper text." },
        })
      );

      try {
        await getSummary("d".repeat(64));
        expect.fail("Expected getSummary to throw 502");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(502);
        expect(apiErr.detail).toBe(
          "Failed to generate structured summary from paper text."
        );
      }
    });
  });

  describe("streamChat", () => {
    it("calls onToken for each token, onSources once, then onDone, in that order", async () => {
      const sseChunks = [
        'event: token\ndata: {"text": "Hello "}\n\n',
        'event: token\ndata: {"text": "world!"}\n\n',
        'event: sources\ndata: [{"page_number": 1, "snippet": "Excerpt"}]\n\n',
        "event: done\ndata: {}\n\n",
      ];

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 200,
          ok: true,
          body: createMockStream(sseChunks),
        })
      );

      const eventsOrder: string[] = [];
      const tokens: string[] = [];
      let receivedSources: ChatSource[] = [];
      let doneCalled = false;

      const handlers: StreamChatHandlers = {
        onToken: (text) => {
          eventsOrder.push(`token: ${text}`);
          tokens.push(text);
        },
        onSources: (sources) => {
          eventsOrder.push("sources");
          receivedSources = sources;
        },
        onDone: () => {
          eventsOrder.push("done");
          doneCalled = true;
        },
        onError: (detail) => {
          eventsOrder.push(`error: ${detail}`);
        },
      };

      await streamChat(
        { doc_hash: "e".repeat(64), message: "Hi" },
        handlers
      );

      expect(tokens).toEqual(["Hello ", "world!"]);
      expect(receivedSources).toEqual([
        { page_number: 1, snippet: "Excerpt" },
      ]);
      expect(doneCalled).toBe(true);
      expect(eventsOrder).toEqual([
        "token: Hello ",
        "token: world!",
        "sources",
        "done",
      ]);
    });

    it("handles a frame split across two chunks", async () => {
      const sseChunks = [
        'event: token\ndata: {"text": "split',
        ' token"}\n\nevent: done\ndata: {}\n\n',
      ];

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 200,
          ok: true,
          body: createMockStream(sseChunks),
        })
      );

      const tokens: string[] = [];
      let doneCalled = false;

      const handlers: StreamChatHandlers = {
        onToken: (text) => tokens.push(text),
        onSources: () => {},
        onDone: () => {
          doneCalled = true;
        },
        onError: () => {},
      };

      await streamChat(
        { doc_hash: "f".repeat(64), message: "Test split" },
        handlers
      );

      expect(tokens).toEqual(["split token"]);
      expect(doneCalled).toBe(true);
    });

    it("calls onError and not onDone when the stream sends an error event", async () => {
      const sseChunks = [
        'event: token\ndata: {"text": "Partial "}\n\n',
        'event: error\ndata: {"detail": "Mid-stream connection error"}\n\n',
      ];

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 200,
          ok: true,
          body: createMockStream(sseChunks),
        })
      );

      let errorDetail = "";
      let doneCalled = false;

      const handlers: StreamChatHandlers = {
        onToken: () => {},
        onSources: () => {},
        onDone: () => {
          doneCalled = true;
        },
        onError: (detail) => {
          errorDetail = detail;
        },
      };

      await streamChat(
        { doc_hash: "1".repeat(64), message: "Trigger mid-stream error" },
        handlers
      );

      expect(errorDetail).toBe("Mid-stream connection error");
      expect(doneCalled).toBe(false);
    });

    it("calls onError when the stream ends without done", async () => {
      const sseChunks = ['event: token\ndata: {"text": "Premature end"}\n\n'];

      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          status: 200,
          ok: true,
          body: createMockStream(sseChunks),
        })
      );

      let errorDetail = "";
      let doneCalled = false;

      const handlers: StreamChatHandlers = {
        onToken: () => {},
        onSources: () => {},
        onDone: () => {
          doneCalled = true;
        },
        onError: (detail) => {
          errorDetail = detail;
        },
      };

      await streamChat(
        { doc_hash: "2".repeat(64), message: "Check abrupt close" },
        handlers
      );

      expect(doneCalled).toBe(false);
      expect(errorDetail).toContain("Stream closed unexpectedly");
    });

    it("passes history correctly and supports abort signal", async () => {
      let passedBody = "";
      global.fetch = vi.fn().mockImplementation((_url, options) => {
        passedBody = options.body;
        return Promise.resolve(
          mockResponse({
            status: 200,
            ok: true,
            body: createMockStream(["event: done\ndata: {}\n\n"]),
          })
        );
      });

      const history: ChatMessage[] = [
        { role: "user", content: "Previous question" },
        { role: "assistant", content: "Previous answer" },
      ];

      const controller = new AbortController();
      let doneCalled = false;

      await streamChat(
        {
          doc_hash: "3".repeat(64),
          message: "Followup",
          history,
        },
        {
          onToken: () => {},
          onSources: () => {},
          onDone: () => {
            doneCalled = true;
          },
          onError: () => {},
        },
        controller.signal
      );

      const parsedJson = JSON.parse(passedBody);
      expect(parsedJson.history).toEqual(history);
      expect(doneCalled).toBe(true);
    });
  });

  describe("SSE parser", () => {
    it("a comment line is ignored; multi-line data: joins with \\n; an invalid JSON payload produces an error without throwing", () => {
      // 1. Comment line is ignored
      const withComment = ": ignore me\nevent: token\ndata: {\"text\": \"hello\"}\n\n";
      const res1 = parseSSE("", withComment);
      expect(res1.events).toHaveLength(1);
      expect(res1.events[0]).toEqual({
        event: "token",
        data: { text: "hello" },
        raw: '{"text": "hello"}',
      });
      expect(res1.remaining).toBe("");

      // 2. Multi-line data joins with \n
      const multiLine = "event: message\ndata: line 1\ndata: line 2\n\n";
      const res2 = parseSSE("", multiLine);
      expect(res2.events).toHaveLength(1);
      // Because line 1\nline 2 is not valid JSON, it becomes an error event
      expect(res2.events[0].event).toBe("error");
      expect(res2.events[0].raw).toBe("line 1\nline 2");
      expect((res2.events[0].data as { detail: string }).detail).toContain(
        "Invalid SSE JSON payload"
      );

      // Valid multi-line JSON joins properly
      const multiLineJson = 'data: {\n' + 'data: "text": "valid"\n' + 'data: }\n\n';
      const res3 = parseSSE("", multiLineJson);
      expect(res3.events).toHaveLength(1);
      expect(res3.events[0].event).toBe("message");
      expect(res3.events[0].data).toEqual({ text: "valid" });

      // 3. Invalid JSON payload produces an error event without throwing
      const invalidJson = "event: token\ndata: {unquoted: text}\n\n";
      let errorThrown = false;
      try {
        const res4 = parseSSE("", invalidJson);
        expect(res4.events).toHaveLength(1);
        expect(res4.events[0].event).toBe("error");
        expect(
          (res4.events[0].data as { detail: string }).detail
        ).toContain("Invalid SSE JSON payload");
      } catch {
        errorThrown = true;
      }
      expect(errorThrown).toBe(false);
    });
  });
});
