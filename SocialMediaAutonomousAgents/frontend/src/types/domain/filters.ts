export type PostFilterParams = {
  since?: string;
  until?: string;
  erMin?: number;
  erMax?: number;
  impressionsMin?: number;
  impressionsMax?: number;
  voice?: string;
  mediaType?: string;
  regenRound?: number;
  lifecycle?: 'early' | 'maturing' | 'mature';
};

export type ReferenceFilterParams = {
  source?: string;
  since?: string;
  entityTag?: string;
  followerTier?: string;
  copyStatus?: 'copied' | 'published' | 'unused';
};

export type PipelineFilterParams = {
  since?: string;
  limit?: number;
  phase?: string;
  status?: string;
  accountId?: string;
};

export type SavedFilterPreset = {
  id: string;
  name: string;
  params: PostFilterParams;
  createdAt: string;
};
