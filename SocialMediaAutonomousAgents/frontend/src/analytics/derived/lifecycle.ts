export type LifecycleBucket = 'early' | 'maturing' | 'mature';

export function lifecycleBucket(postedAt: string | undefined): LifecycleBucket {
  if (!postedAt) {
    return 'early';
  }
  const t = Date.parse(postedAt);
  if (Number.isNaN(t)) {
    return 'early';
  }
  const hours = (Date.now() - t) / 3600000;
  if (hours < 6) {
    return 'early';
  }
  if (hours < 48) {
    return 'maturing';
  }
  return 'mature';
}
