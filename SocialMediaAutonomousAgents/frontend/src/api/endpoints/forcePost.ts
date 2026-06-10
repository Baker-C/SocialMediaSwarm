import type { ForcePostStreamEvent } from '../../lib/forcePostSteps';
import { apiPrefix, parseHttpError } from '../client';

function parseSseData(line: string): ForcePostStreamEvent | null {
  const payload = line.startsWith('data: ') ? line.slice(6) : line;
  if (!payload.trim()) {
    return null;
  }
  try {
    return JSON.parse(payload) as ForcePostStreamEvent;
  } catch {
    return null;
  }
}

export async function streamForcePost(
  apiBase: string,
  accountId: string,
  onEvent: (event: ForcePostStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/accounts/${encodeURIComponent(accountId)}/force-post`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    signal,
  });
  if (!res.ok) {
    throw new Error(await parseHttpError(res));
  }
  if (!res.body) {
    throw new Error('No response body from force post stream');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const chunk of parts) {
      for (const line of chunk.split('\n')) {
        const event = parseSseData(line);
        if (event) {
          onEvent(event);
        }
      }
    }
  }

  if (buffer.trim()) {
    for (const line of buffer.split('\n')) {
      const event = parseSseData(line);
      if (event) {
        onEvent(event);
      }
    }
  }
}
