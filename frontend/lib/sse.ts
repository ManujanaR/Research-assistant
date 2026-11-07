export interface ParsedSSEEvent {
  event: string;
  data: unknown;
  raw?: string;
}

export interface ParseSSEResult {
  events: ParsedSSEEvent[];
  remaining: string;
}

/**
 * Pure function over a string buffer that parses complete SSE frames.
 *
 * Takes existing buffer and incoming text chunk, and returns complete events
 * plus any remaining incomplete frame buffer.
 * - Handles frames separated by \n\n or \r\n\r\n.
 * - Joins multiple data: lines with \n.
 * - Ignores comment lines starting with :.
 * - Parses data as JSON; invalid JSON produces an error event instead of throwing.
 */
export function parseSSE(buffer: string, chunk: string): ParseSSEResult {
  const full = buffer + chunk;
  const delimiterRegex = /\r?\n\r?\n/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const events: ParsedSSEEvent[] = [];

  while ((match = delimiterRegex.exec(full)) !== null) {
    const frame = full.slice(lastIndex, match.index);
    lastIndex = match.index + match[0].length;

    if (!frame.trim()) {
      continue;
    }

    const lines = frame.split(/\r?\n/);
    let eventName = "";
    const dataLines: string[] = [];

    for (const line of lines) {
      if (line.startsWith(":")) {
        // Comment line, ignore as per SSE specification
        continue;
      }
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        let value = line.slice(5);
        if (value.startsWith(" ")) {
          value = value.slice(1);
        }
        dataLines.push(value);
      } else if (line === "data") {
        dataLines.push("");
      }
    }

    if (dataLines.length === 0 && !eventName) {
      continue;
    }

    const rawData = dataLines.join("\n");
    let parsedData: unknown = {};
    let finalEvent = eventName || "message";

    if (rawData.length > 0) {
      try {
        parsedData = JSON.parse(rawData);
      } catch (err) {
        finalEvent = "error";
        parsedData = {
          detail: `Invalid SSE JSON payload: ${
            err instanceof Error ? err.message : String(err)
          }`,
        };
      }
    }

    events.push({
      event: finalEvent,
      data: parsedData,
      raw: rawData,
    });
  }

  return {
    events,
    remaining: full.slice(lastIndex),
  };
}

export const parseSSEBuffer = parseSSE;
