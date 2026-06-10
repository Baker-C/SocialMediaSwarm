import type { PostFilterParams } from '../../types';
import type { EnrichedTrackedPost } from '../../types/domain/trackedPost';
import { lifecycleBucket } from '../derived/lifecycle';

export function filterPosts(
  posts: EnrichedTrackedPost[],
  filters: PostFilterParams
): EnrichedTrackedPost[] {
  return posts.filter((post) => {
    if (filters.since && (post.posted_at ?? '') < filters.since) {
      return false;
    }
    if (filters.until && (post.posted_at ?? '') > filters.until) {
      return false;
    }
    if (filters.erMin !== undefined) {
      const er = post.engagement_rate ?? -Infinity;
      if (er < filters.erMin) {
        return false;
      }
    }
    if (filters.erMax !== undefined) {
      const er = post.engagement_rate ?? Infinity;
      if (er > filters.erMax) {
        return false;
      }
    }
    if (filters.impressionsMin !== undefined) {
      const imp = post.impression_count ?? -Infinity;
      if (imp < filters.impressionsMin) {
        return false;
      }
    }
    if (filters.impressionsMax !== undefined) {
      const imp = post.impression_count ?? Infinity;
      if (imp > filters.impressionsMax) {
        return false;
      }
    }
    if (filters.voice) {
      const label = post.creation_metrics?.voice_version_label ?? '';
      if (!label.toLowerCase().includes(filters.voice.toLowerCase())) {
        return false;
      }
    }
    if (filters.mediaType) {
      const media = post.primary_media_type ?? post.media_types?.[0] ?? '';
      if (media !== filters.mediaType) {
        return false;
      }
    }
    if (filters.regenRound !== undefined) {
      const round = post.creation_metrics?.regeneration_round ?? 0;
      if (round !== filters.regenRound) {
        return false;
      }
    }
    if (filters.lifecycle) {
      if (lifecycleBucket(post.posted_at) !== filters.lifecycle) {
        return false;
      }
    }
    return true;
  });
}

export function postTableRows(posts: EnrichedTrackedPost[]) {
  return posts.map((post) => ({
    ...post,
    refScoreAtPick:
      typeof post.creation_metrics?.source_reference_metrics_at_pick?.popularity_score ===
      'number'
        ? (post.creation_metrics.source_reference_metrics_at_pick.popularity_score as number)
        : null,
  }));
}
