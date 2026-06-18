import { apiPrefix, parseHttpError } from '../client';
import { authHeaders } from '../auth';
import type { BuilderChatRequest, BuilderStreamEvent } from '../../types/domain/builder';

function parseSse(line: string): BuilderStreamEvent | null {
  const payload = line.startsWith('data: ') ? line.slice(6) : line;
  if (!payload.trim()) return null;
  try {
    return JSON.parse(payload) as BuilderStreamEvent;
  } catch {
    return null;
  }
}

// `req` is doc 10's BuilderChatRequest: { account_id, mode, messages[], approve }.
// The full message history is posted every turn (doc 10's server is stateless; the
// client echoes prior proposed_spec/validation_errors back in `messages` — doc 10 §6.1).
export async function streamBuilderChat(
  apiBase: string,
  req: BuilderChatRequest,
  onEvent: (event: BuilderStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/agent-builder/chat`, {   // doc 10 §4: POST /api/agent-builder/chat
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) throw new Error(await parseHttpError(res));
  if (!res.body) throw new Error('No response body from builder stream');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  // identical chunk/line loop to forcePost.ts:40-65
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const chunk of parts)
      for (const line of chunk.split('\n')) {
        const ev = parseSse(line);
        if (ev) onEvent(ev);
      }
  }
  if (buffer.trim())
    for (const line of buffer.split('\n')) {
      const ev = parseSse(line);
      if (ev) onEvent(ev);
    }
}
