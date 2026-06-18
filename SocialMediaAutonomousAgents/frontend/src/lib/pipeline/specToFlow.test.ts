import { flowStepIds, flowFromSpec } from './specToFlow';
import type { PipelineSpec } from '../../types/domain/pipelineSpec';

// Baseline spec mirroring doc 04 default_pipeline_spec — the 10-leaf SENSE+ACT tree.
const baselineSpec: PipelineSpec = {
  account_id: 'test',
  status: 'champion',
  steps: [
    {
      kind: 'step',
      id: 'load_account_bundle',
      tool_id: 'data.account_profile',
      reads: [],
      writes: ['account_bundle'],
      purpose: 'Load account profile and metrics',
    },
    {
      kind: 'step',
      id: 'fetch_search_references',
      tool_id: 'data.search_fetch',
      reads: [],
      writes: ['search_references'],
      purpose: 'Fetch search results for the niche',
    },
    {
      kind: 'step',
      id: 'collect_external_references',
      tool_id: 'deterministic.collect_external',
      reads: ['search_references'],
      writes: ['external_references'],
      purpose: 'Collect and deduplicate external references',
    },
    {
      kind: 'step',
      id: 'fetch_own_post_history',
      tool_id: 'data.own_posts_fetch',
      reads: ['account_bundle'],
      writes: ['own_posts'],
      purpose: 'Fetch own post history',
    },
    {
      kind: 'parallel',
      id: 'summarize_for_compose',
      children: [
        {
          kind: 'chain',
          id: 'analyze_external_references',
          children: [
            {
              kind: 'step',
              id: 'rank_external_references',
              tool_id: 'deterministic.rank_references',
              reads: ['external_references'],
              writes: ['ranked_external'],
              purpose: 'Rank external references by engagement',
            },
            {
              kind: 'step',
              id: 'brief_external_references',
              tool_id: 'llm.brief',
              reads: ['ranked_external'],
              writes: ['brief_external'],
              purpose: 'LLM pattern summary for external',
            },
          ],
        },
        {
          kind: 'chain',
          id: 'analyze_own_posts',
          children: [
            {
              kind: 'step',
              id: 'rank_own_posts',
              tool_id: 'deterministic.rank_own_posts',
              reads: ['own_posts'],
              writes: ['ranked_own'],
              purpose: 'Rank own posts by voice signal',
            },
            {
              kind: 'step',
              id: 'brief_own_posts',
              tool_id: 'llm.brief_own',
              reads: ['ranked_own'],
              writes: ['brief_own'],
              purpose: 'LLM voice brief for own posts',
            },
          ],
        },
      ],
    },
    {
      kind: 'step',
      id: 'compose_until_safe',
      tool_id: 'llm.compose_until_safe',
      reads: ['brief_external', 'brief_own'],
      writes: ['composed_post'],
      purpose: 'Compose post using voice and references',
    },
    {
      kind: 'step',
      id: 'publish_post',
      tool_id: 'data.publish_post',
      reads: ['composed_post'],
      writes: ['published'],
      purpose: 'Publish the post to X',
    },
  ],
};

describe('specToFlow', () => {
  it('flowStepIds produces the exact 10-leaf baseline list', () => {
    const ids = flowStepIds(baselineSpec);
    const expected = [
      'load_account_bundle',
      'fetch_search_references',
      'collect_external_references',
      'fetch_own_post_history',
      'summarize_for_compose.analyze_external_references.rank_external_references',
      'summarize_for_compose.analyze_external_references.brief_external_references',
      'summarize_for_compose.analyze_own_posts.rank_own_posts',
      'summarize_for_compose.analyze_own_posts.brief_own_posts',
      'compose_until_safe',
      'publish_post',
    ];
    expect(ids).toEqual(expected);
  });

  it('flowFromSpec renders one parallel row with two branches and two ACT leaves', () => {
    const sections = flowFromSpec(baselineSpec);
    expect(sections).toHaveLength(2); // orchestrator-pre + runbook
    const runbook = sections.find(s => s.id === 'runbook');
    expect(runbook).toBeDefined();
    if (!runbook) return;

    // Count rows: 4 top-level steps + 1 parallel + 2 ACT leaves = 7 rows
    expect(runbook.rows).toHaveLength(7);

    // The parallel row should have 2 branches
    const parallelRow = runbook.rows.find(r => r.type === 'parallel');
    expect(parallelRow).toBeDefined();
    if (!parallelRow || parallelRow.type !== 'parallel') return;
    expect(parallelRow.branches).toHaveLength(2);

    // Each branch should have 2 steps (rank + brief)
    expect(parallelRow.branches[0].steps).toHaveLength(2);
    expect(parallelRow.branches[1].steps).toHaveLength(2);
  });
});
