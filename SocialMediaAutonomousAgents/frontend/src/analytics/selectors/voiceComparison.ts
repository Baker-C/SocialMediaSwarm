import type { TrackedPost, VoiceRevision } from '../../types';

export type VoiceVersionStats = {
  seq: number | null;
  label: string;
  postCount: number;
  avgEr: number | null;
  avgImpressions: number | null;
};

export function compareVoiceVersions(
  posts: TrackedPost[],
  revisions: VoiceRevision[]
): VoiceVersionStats[] {
  const bySeq = new Map<number, { label: string; ers: number[]; impressions: number[] }>();

  for (const rev of revisions) {
    bySeq.set(rev.seq, { label: rev.label, ers: [], impressions: [] });
  }

  for (const post of posts) {
    const seq = post.creation_metrics?.voice_version_seq;
    const label = post.creation_metrics?.voice_version_label ?? `v${seq ?? '?'}`;
    const key = seq ?? -1;
    const entry = bySeq.get(key) ?? { label, ers: [], impressions: [] };
    if (post.engagement_rate != null) {
      entry.ers.push(post.engagement_rate);
    }
    if (post.impression_count != null) {
      entry.impressions.push(post.impression_count);
    }
    bySeq.set(key, entry);
  }

  const rows: VoiceVersionStats[] = [];
  bySeq.forEach((data, seq) => {
    rows.push({
      seq: seq >= 0 ? seq : null,
      label: data.label,
      postCount: data.ers.length || data.impressions.length,
      avgEr: data.ers.length ? data.ers.reduce((a, b) => a + b, 0) / data.ers.length : null,
      avgImpressions: data.impressions.length
        ? data.impressions.reduce((a, b) => a + b, 0) / data.impressions.length
        : null,
    });
  });
  return rows.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
}

export function revisionTimeline(revisions: VoiceRevision[]) {
  return [...revisions].sort((a, b) => a.seq - b.seq);
}
