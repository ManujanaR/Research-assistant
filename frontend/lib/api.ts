import { parseSSE } from "./sse";

export interface UploadResponse {
  doc_hash: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  chunk_count: number;
}

export interface SummaryResponse {
  title_authors_abstract: string;
  problem_statement: string;
  methodology: string;
  key_results: string;
  conclusion: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSource {
  page_number: number | null;
  snippet: string;
}

export interface UserResponse {
  id: string;
  email: string;
}

export interface ExportSource {
  page_number?: number | null;
  snippet?: string | null;
}

export interface ExportMessage {
  role: "user" | "assistant";
  text: string;
  sources?: ExportSource[];
}

export interface ExportResponse {
  blob: Blob;
  filename: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export interface StreamChatParams {
  doc_hash: string;
  message: string;
  history?: ChatMessage[];
}

export interface StreamChatHandlers {
  onToken: (text: string) => void;
  onSources: (sources: ChatSource[]) => void;
  onDone: () => void;
  onError: (detail: string) => void;
}

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:8000";

interface ValidationErrorItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

interface ErrorResponseBody {
  detail?: string | ValidationErrorItem[] | unknown;
}

export async function parseErrorResponse(response: Response): Promise<ApiError> {
  const status = response.status;
  let detail: string | undefined;

  try {
    const data = (await response.json()) as ErrorResponseBody;
    if (typeof data?.detail === "string") {
      detail = data.detail;
    } else if (Array.isArray(data?.detail)) {
      const messages = data.detail
        .map((item) => {
          if (typeof item === "object" && item !== null && "msg" in item) {
            const errItem = item as ValidationErrorItem;
            return errItem.msg ?? "";
          }
          return String(item);
        })
        .filter((msg) => msg.length > 0);
      detail = messages.join("; ");
    } else if (data?.detail) {
      detail = String(data.detail);
    }
  } catch {
    // Non-JSON response fallback
  }

  // Canonical mapping for authentication status codes per DESIGN.md section 4.9
  if (status === 401) {
    if (!detail || detail.toLowerCase().includes("unauthorized") || detail === "Not authenticated") {
      detail = detail || "Email or password is incorrect.";
    }
  } else if (status === 404) {
    detail = detail || "Document not found. Upload the PDF first.";
  } else if (status === 409) {
    detail = detail || "An account with this email already exists.";
  } else if (status === 422) {
    if (!detail || detail.toLowerCase().includes("at least 8") || detail.toLowerCase().includes("password")) {
      detail = "Password must be at least 8 characters.";
    }
  } else if (status === 429) {
    detail = detail || "Too many attempts. Try again in a few minutes.";
  }

  return new ApiError(
    status,
    detail || response.statusText || `Request failed with status ${status}`
  );
}

export async function signUp(
  email: string,
  password: string
): Promise<UserResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/auth/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as UserResponse;
}

export async function signIn(
  email: string,
  password: string
): Promise<UserResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/auth/signin`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as UserResponse;
}

export async function signOut(): Promise<{ status: string }> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/auth/signout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as { status: string };
}

export async function getMe(): Promise<UserResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/auth/me`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as UserResponse;
}

export async function uploadPdf(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/upload`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  return (await response.json()) as UploadResponse;
}

export async function getSummary(docHash: string): Promise<SummaryResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/summary`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({ doc_hash: docHash }),
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  const data = (await response.json()) as SummaryResponse;
  return {
    title_authors_abstract: data.title_authors_abstract,
    problem_statement: data.problem_statement,
    methodology: data.methodology,
    key_results: data.key_results,
    conclusion: data.conclusion,
  };
}

export async function streamChat(
  params: StreamChatParams,
  handlers: StreamChatHandlers,
  signal?: AbortSignal
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        doc_hash: params.doc_hash,
        message: params.message,
        history: params.history ?? [],
      }),
      signal,
    });
  } catch (err) {
    if (signal?.aborted || (err instanceof Error && err.name === "AbortError")) {
      return;
    }
    const message = err instanceof Error ? err.message : "Network error";
    handlers.onError(message);
    throw new ApiError(0, message);
  }

  if (!response.ok) {
    const error = await parseErrorResponse(response);
    handlers.onError(error.detail);
    throw error;
  }

  if (!response.body) {
    const detail = "Response body stream is not available";
    handlers.onError(detail);
    throw new ApiError(response.status, detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finished = false;

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        return;
      }

      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      const chunk = decoder.decode(value, { stream: true });
      const parsed = parseSSE(buffer, chunk);
      buffer = parsed.remaining;

      for (const ev of parsed.events) {
        if (ev.event === "token") {
          const data = ev.data as { text?: string };
          if (typeof data?.text === "string") {
            handlers.onToken(data.text);
          }
        } else if (ev.event === "sources") {
          const sources = Array.isArray(ev.data)
            ? (ev.data as ChatSource[])
            : [];
          handlers.onSources(sources);
        } else if (ev.event === "done") {
          finished = true;
          handlers.onDone();
        } else if (ev.event === "error") {
          finished = true;
          const data = ev.data as { detail?: string };
          const detail =
            typeof data?.detail === "string"
              ? data.detail
              : "Unknown stream error";
          handlers.onError(detail);
        }
      }
    }

    if (buffer.trim()) {
      const finalParsed = parseSSE(buffer, "\n\n");
      for (const ev of finalParsed.events) {
        if (ev.event === "token") {
          const data = ev.data as { text?: string };
          if (typeof data?.text === "string") {
            handlers.onToken(data.text);
          }
        } else if (ev.event === "sources") {
          const sources = Array.isArray(ev.data)
            ? (ev.data as ChatSource[])
            : [];
          handlers.onSources(sources);
        } else if (ev.event === "done") {
          finished = true;
          handlers.onDone();
        } else if (ev.event === "error") {
          finished = true;
          const data = ev.data as { detail?: string };
          const detail =
            typeof data?.detail === "string"
              ? data.detail
              : "Unknown stream error";
          handlers.onError(detail);
        }
      }
    }
  } catch (err) {
    if (signal?.aborted || (err instanceof Error && err.name === "AbortError")) {
      return;
    }
    finished = true;
    const detail = err instanceof Error ? err.message : "Stream read error";
    handlers.onError(detail);
    throw new ApiError(0, detail);
  }

  if (!finished) {
    handlers.onError("Stream closed unexpectedly before completion");
  }
}

export async function exportReport(
  docHash: string,
  messages: ExportMessage[] = []
): Promise<ExportResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/export`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        doc_hash: docHash,
        messages: messages.slice(-200),
      }),
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network error");
  }

  if (!response.ok) {
    throw await parseErrorResponse(response);
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get("Content-Disposition") || "";
  let filename = `mitra-report-${docHash.slice(0, 8)}.docx`;
  const match = contentDisposition.match(/filename="?([^";]+)"?/i);
  if (match && match[1]) {
    filename = match[1].trim();
  }

  return { blob, filename };
}

