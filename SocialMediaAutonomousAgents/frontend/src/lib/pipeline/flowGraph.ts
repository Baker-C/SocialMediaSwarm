export type FlowLayer = 'entry' | 'orchestrator' | 'runbook' | 'tools' | 'persistence' | 'external';

export type FlowNodeKind = 'step' | 'satellite';

export type FlowNodeDef = {
  id: string;
  label: string;
  subtext?: string;
  layer: FlowLayer;
  kind?: FlowNodeKind;
  /** Highlight when any of these step ids are active. */
  watchSteps?: string[];
};

export const PIPELINE_FLOW_NODES: FlowNodeDef[] = [
  { id: 'start', label: 'Force post', subtext: 'operator trigger', layer: 'entry' },
  { id: 'load_account', label: 'Load account', subtext: 'reload + skip guards', layer: 'orchestrator' },
  { id: 'post_lock', label: 'Post lock', subtext: 'cooldown · file · slot', layer: 'orchestrator' },
  {
    id: 'load_account_bundle',
    label: 'Account bundle',
    subtext: 'profile + metrics',
    layer: 'runbook',
  },
  {
    id: 'fetch_external_references.fetch_timeline_references',
    label: 'Timeline fetch',
    subtext: 'following timeline',
    layer: 'runbook',
  },
  {
    id: 'fetch_external_references.fetch_search_references',
    label: 'Search fetch',
    subtext: 'optional queries',
    layer: 'runbook',
  },
  {
    id: 'merge_external_references',
    label: 'Merge references',
    subtext: 'dedupe by tweet id',
    layer: 'runbook',
  },
  {
    id: 'fetch_own_post_history',
    label: 'Own posts',
    subtext: 'engagement history',
    layer: 'runbook',
  },
  {
    id: 'summarize_for_compose.analyze_external_references.rank_external_references',
    label: 'Rank external',
    subtext: 'engagement score',
    layer: 'runbook',
  },
  {
    id: 'summarize_for_compose.analyze_external_references.brief_external_references',
    label: 'Brief external',
    subtext: 'LLM pattern summary',
    layer: 'runbook',
  },
  {
    id: 'summarize_for_compose.analyze_own_posts.rank_own_posts',
    label: 'Rank own posts',
    subtext: 'voice signals',
    layer: 'runbook',
  },
  {
    id: 'summarize_for_compose.analyze_own_posts.brief_own_posts',
    label: 'Brief own posts',
    subtext: 'LLM voice brief',
    layer: 'runbook',
  },
  { id: 'compose', label: 'Compose', subtext: 'Claude + voice', layer: 'orchestrator' },
  { id: 'safety', label: 'Safety', subtext: 'niche · policy', layer: 'orchestrator' },
  { id: 'publish', label: 'Publish', subtext: 'post to X', layer: 'orchestrator' },
  { id: 'complete', label: 'Complete', subtext: 'tracked post saved', layer: 'orchestrator' },
  {
    id: 'claude',
    label: 'Claude',
    subtext: 'LLM inference',
    layer: 'external',
    kind: 'satellite',
    watchSteps: [
      'summarize_for_compose.analyze_external_references.brief_external_references',
      'summarize_for_compose.analyze_own_posts.brief_own_posts',
      'compose',
    ],
  },
  {
    id: 'x_api',
    label: 'X API',
    subtext: 'timeline · search · post',
    layer: 'external',
    kind: 'satellite',
    watchSteps: [
      'fetch_external_references.fetch_timeline_references',
      'fetch_external_references.fetch_search_references',
      'publish',
    ],
  },
  {
    id: 'ravendb',
    label: 'RavenDB',
    subtext: 'accounts · locks · posts',
    layer: 'persistence',
    kind: 'satellite',
    watchSteps: ['post_lock', 'publish'],
  },
];

export const PIPELINE_FLOW_NODE_IDS = PIPELINE_FLOW_NODES.map((n) => n.id);

export const PIPELINE_FLOW_LANE_ORDER: FlowLayer[] = [
  'entry',
  'orchestrator',
  'runbook',
  'tools',
  'persistence',
  'external',
];

export const PIPELINE_FLOW_LANE_LABELS: Record<FlowLayer, string> = {
  entry: 'Entry',
  orchestrator: 'Orchestrator',
  runbook: 'Reference runbook',
  tools: 'Tools',
  persistence: 'Persistence',
  external: 'External',
};
