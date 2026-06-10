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

export function formatRate(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return value.toFixed(digits);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMetricDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  if (value === 0) {
    return '±0';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return value.toLocaleString();
}

export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return String(value);
}

export function isStaleFetch(iso: string | null | undefined, maxHours = 2): boolean {
  if (!iso) {
    return true;
  }
  const t = Date.parse(iso);
  if (Number.isNaN(t)) {
    return true;
  }
  return Date.now() - t > maxHours * 3600000;
}
