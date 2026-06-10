import type { PostFilterParams, ReferenceFilterParams, PipelineFilterParams } from '../types';

function parseNumber(value: string | null): number | undefined {
  if (!value?.trim()) {
    return undefined;
  }
  const n = Number(value);
  return Number.isNaN(n) ? undefined : n;
}

function parseIntParam(value: string | null): number | undefined {
  if (!value?.trim()) {
    return undefined;
  }
  const n = parseInt(value, 10);
  return Number.isNaN(n) ? undefined : n;
}

export function postFiltersFromSearchParams(params: URLSearchParams): PostFilterParams {
  const lifecycle = params.get('lifecycle');
  return {
    since: params.get('since') ?? undefined,
    until: params.get('until') ?? undefined,
    erMin: parseNumber(params.get('erMin')),
    erMax: parseNumber(params.get('erMax')),
    impressionsMin: parseNumber(params.get('impressionsMin')),
    impressionsMax: parseNumber(params.get('impressionsMax')),
    voice: params.get('voice') ?? undefined,
    mediaType: params.get('mediaType') ?? undefined,
    regenRound: parseIntParam(params.get('regenRound')),
    lifecycle:
      lifecycle === 'early' || lifecycle === 'maturing' || lifecycle === 'mature'
        ? lifecycle
        : undefined,
  };
}

export function postFiltersToSearchParams(
  filters: PostFilterParams,
  existing?: URLSearchParams
): URLSearchParams {
  const params = new URLSearchParams(existing?.toString() ?? '');
  const keys: (keyof PostFilterParams)[] = [
    'since',
    'until',
    'erMin',
    'erMax',
    'impressionsMin',
    'impressionsMax',
    'voice',
    'mediaType',
    'regenRound',
    'lifecycle',
  ];
  for (const key of keys) {
    params.delete(key);
  }
  if (filters.since) {
    params.set('since', filters.since);
  }
  if (filters.until) {
    params.set('until', filters.until);
  }
  if (filters.erMin !== undefined) {
    params.set('erMin', String(filters.erMin));
  }
  if (filters.erMax !== undefined) {
    params.set('erMax', String(filters.erMax));
  }
  if (filters.impressionsMin !== undefined) {
    params.set('impressionsMin', String(filters.impressionsMin));
  }
  if (filters.impressionsMax !== undefined) {
    params.set('impressionsMax', String(filters.impressionsMax));
  }
  if (filters.voice) {
    params.set('voice', filters.voice);
  }
  if (filters.mediaType) {
    params.set('mediaType', filters.mediaType);
  }
  if (filters.regenRound !== undefined) {
    params.set('regenRound', String(filters.regenRound));
  }
  if (filters.lifecycle) {
    params.set('lifecycle', filters.lifecycle);
  }
  return params;
}

export function referenceFiltersFromSearchParams(params: URLSearchParams): ReferenceFilterParams {
  const copyStatus = params.get('copyStatus');
  return {
    source: params.get('source') ?? undefined,
    since: params.get('since') ?? undefined,
    entityTag: params.get('entityTag') ?? undefined,
    followerTier: params.get('followerTier') ?? undefined,
    copyStatus:
      copyStatus === 'copied' || copyStatus === 'published' || copyStatus === 'unused'
        ? copyStatus
        : undefined,
  };
}

export function referenceFiltersToSearchParams(
  filters: ReferenceFilterParams,
  existing?: URLSearchParams
): URLSearchParams {
  const params = new URLSearchParams(existing?.toString() ?? '');
  for (const key of ['source', 'since', 'entityTag', 'followerTier', 'copyStatus']) {
    params.delete(key);
  }
  if (filters.source) {
    params.set('source', filters.source);
  }
  if (filters.since) {
    params.set('since', filters.since);
  }
  if (filters.entityTag) {
    params.set('entityTag', filters.entityTag);
  }
  if (filters.followerTier) {
    params.set('followerTier', filters.followerTier);
  }
  if (filters.copyStatus) {
    params.set('copyStatus', filters.copyStatus);
  }
  return params;
}

export function pipelineFiltersFromSearchParams(params: URLSearchParams): PipelineFilterParams {
  return {
    since: params.get('since') ?? undefined,
    limit: parseIntParam(params.get('limit')),
    phase: params.get('phase') ?? undefined,
    status: params.get('status') ?? undefined,
    accountId: params.get('accountId') ?? undefined,
  };
}

export function defaultSinceDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString();
}
