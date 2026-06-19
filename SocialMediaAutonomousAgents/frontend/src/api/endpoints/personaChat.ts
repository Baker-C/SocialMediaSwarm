import { apiFetch, apiPrefix, parseHttpError, apiBaseUrl } from '../client';
import { authHeaders } from '../auth';
import type { PersonaChatRequest, PersonaStreamEvent } from '../../types/domain/persona';

function parseSse(line: string): PersonaStreamEvent | null {
  const payload = line.startsWith('data: ') ? line.slice(6) : line;
  if (!payload.trim()) return null;
  try {
    return JSON.parse(payload) as PersonaStreamEvent;
  } catch {
    return null;
  }
}

// Stateless multi-turn: the full message history (+ prior proposal) is posted every
// turn (plan 03 §1). Copy of streamBuilderChat — SSE via fetch + ReadableStream reader.
export async function streamPersonaChat(
  apiBase: string,
  req: PersonaChatRequest,
  onEvent: (event: PersonaStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/persona/chat`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) throw new Error(await parseHttpError(res));
  if (!res.body) throw new Error('No response body from persona stream');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
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

// Review-stage regenerate (plan 04 §3). Posts only non-empty prompts; the response
// includes only the keys produced for those prompts.
export async function regenerateImages(body: {
  avatar_prompt?: string;
  header_prompt?: string;
}): Promise<{ avatar_asset_id?: string; header_asset_id?: string }> {
  return apiFetch('/persona/regenerate-images', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// Media bytes route for <img src> (plan 04 §3: GET /api/media/{asset_id}).
export function mediaUrl(assetId: string): string {
  return `${apiPrefix(apiBaseUrl())}/media/${encodeURIComponent(assetId)}`;
}
