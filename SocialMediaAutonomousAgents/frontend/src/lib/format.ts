export function formatAge(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return '—';
  }
  const ms = Date.now() - t;
  const days = Math.floor(ms / 86400000);
  if (days >= 30) {
    return `${Math.floor(days / 30)}mo`;
  }
  if (days >= 1) {
    return `${days}d`;
  }
  const hours = Math.floor(ms / 3600000);
  if (hours >= 1) {
    return `${hours}h`;
  }
  const mins = Math.floor(ms / 60000);
  return `${Math.max(0, mins)}m`;
}

export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return '—';
  }
  return new Date(t).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatGrowth(n: number | null | undefined): string {
  if (n === null || n === undefined) {
    return 'Not tracked yet';
  }
  if (n === 0) {
    return '±0 vs baseline';
  }
  const sign = n > 0 ? '+' : '';
  return `${sign}${n} vs baseline`;
}
