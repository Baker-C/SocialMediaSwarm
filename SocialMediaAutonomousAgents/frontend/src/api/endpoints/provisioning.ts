import { apiFetch, apiPrefix, parseHttpError } from '../client';
import { authHeaders } from '../auth';
import type {
  ProvisioningControlAction,
  ProvisioningStatusEvent,
} from '../../types/domain/persona';

// plan 05 §3: POST /api/provisioning/{id}/start (202).
export async function startProvisioning(accountId: string): Promise<{ ok: boolean }> {
  return apiFetch(`/provisioning/${encodeURIComponent(accountId)}/start`, { method: 'POST' });
}

// plan 05 §3/§4: POST /api/provisioning/{id}/control — operator continue/cancel.
export async function sendControl(
  accountId: string,
  action: ProvisioningControlAction
): Promise<{ ok: boolean }> {
  return apiFetch(`/provisioning/${encodeURIComponent(accountId)}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
}

function parseSse(line: string): ProvisioningStatusEvent | null {
  const payload = line.startsWith('data: ') ? line.slice(6) : line;
  if (!payload.trim()) return null;
  try {
    return JSON.parse(payload) as ProvisioningStatusEvent;
  } catch {
    return null;
  }
}

// plan 05 §4: GET SSE /api/provisioning/{id}/status — worker tails provisioning.status.
export async function streamProvisioningStatus(
  apiBase: string,
  accountId: string,
  onEvent: (event: ProvisioningStatusEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/provisioning/${encodeURIComponent(accountId)}/status`, {
    method: 'GET',
    headers: { Accept: 'text/event-stream', ...authHeaders() },
    signal,
  });
  if (!res.ok) throw new Error(await parseHttpError(res));
  if (!res.body) throw new Error('No response body from provisioning status stream');

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
