/** Map granular pipeline step ids onto the legacy linear force-post tracker. */

const RUNBOOK_TO_LINEAR: Record<string, string> = {
  load_account_bundle: 'fetch_profile',
  'fetch_external_references.fetch_timeline_references': 'fetch_timeline',
  'fetch_external_references.fetch_search_references': 'fetch_timeline',
  merge_external_references: 'fetch_timeline',
  fetch_own_post_history: 'fetch_profile',
  'summarize_for_compose.analyze_external_references.rank_external_references': 'rank_references',
  'summarize_for_compose.analyze_external_references.brief_external_references': 'rank_references',
  'summarize_for_compose.analyze_own_posts.rank_own_posts': 'rank_references',
  'summarize_for_compose.analyze_own_posts.brief_own_posts': 'rank_references',
};

const ORCHESTRATOR_LINEAR = new Set([
  'start',
  'load_account',
  'post_lock',
  'compose',
  'safety',
  'publish',
  'complete',
]);

export function toLinearStepId(stepId: string): string | null {
  if (ORCHESTRATOR_LINEAR.has(stepId)) {
    return stepId;
  }
  return RUNBOOK_TO_LINEAR[stepId] ?? null;
}
