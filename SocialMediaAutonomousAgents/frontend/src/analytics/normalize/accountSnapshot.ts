import type { AccountSnapshot } from '../../types';

export type NormalizedSnapshotPoint = {
  capturedAt: string;
  label: string;
  followers: number;
  totalViews: number;
  totalLikes: number;
  postsTotal: number;
};

export function normalizeAccountSnapshots(
  snapshots: AccountSnapshot[]
): NormalizedSnapshotPoint[] {
  return [...snapshots]
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
    .map((s) => ({
      capturedAt: s.created_at,
      label: new Date(s.created_at).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
      }),
      followers: s.followers ?? 0,
      totalViews: s.total_views ?? 0,
      totalLikes: s.total_likes ?? 0,
      postsTotal: s.posts_total ?? 0,
    }));
}
