/* ────────────────────────────────────────────────────────────────────────────
 * ⚠️  KEEP IN SYNC WITH THE BACKEND RUNBOOK.
 *
 * This graph is a faithful mirror of the post-tick pipeline defined in
 *   backend/app/pipeline/runbooks/post_tick.py  (POST_TICK_REFERENCE_STEPS)
 * plus the orchestrator stages that wrap it (load account → post lock → … →
 * compose → safety → publish → complete).
 *
 * Each step `id` MUST equal the emitted progress `step_id` — i.e. the dotted id
 * produced by `flatten_steps` (e.g.
 *   summarize_for_compose.analyze_external_references.rank_external_references).
 * If an id drifts, the node silently stops lighting up during a live run.
 *
 * The structure is intentionally literal about execution order: `parallel()` in
 * the runbook declares data-independent branches but the engine runs them
 * SEQUENTIALLY (branch A fully, then branch B). The diagram says so on purpose.
 *
 * When you edit the runbook, edit this file — and vice versa.
 * ──────────────────────────────────────────────────────────────────────────── */

/** External systems a step talks to, shown as a side call-out on the node. */
export type FlowExternal = 'claude' | 'x_api' | 'ravendb';

export const EXTERNAL_LABELS: Record<FlowExternal, string> = {
  claude: 'Claude',
  x_api: 'X API',
  ravendb: 'RavenDB',
};

export type FlowNodeDef = {
  /** Must match the emitted progress step_id for live status to work. */
  id: string;
  label: string;
  subtext?: string;
  external?: FlowExternal;
};

export type FlowBranch = {
  id: string;
  label: string;
  /** Sequential chain within the branch (rank → brief). */
  steps: FlowNodeDef[];
};

export type FlowRow =
  | { type: 'step'; node: FlowNodeDef }
  | {
      type: 'parallel';
      id: string;
      label: string;
      /** Honest note about how the "parallel" block actually executes. */
      note: string;
      branches: FlowBranch[];
    };

export type FlowSection = {
  id: string;
  /** When set, the section renders inside a labelled border (the runbook). */
  label?: string;
  rows: FlowRow[];
};

export const PIPELINE_FLOW: FlowSection[] = [
  {
    id: 'orchestrator-pre',
    rows: [
      { type: 'step', node: { id: 'start', label: 'Force post', subtext: 'operator trigger' } },
      {
        type: 'step',
        node: { id: 'load_account', label: 'Load account', subtext: 'reload + skip guards' },
      },
      {
        type: 'step',
        node: {
          id: 'post_lock',
          label: 'Post lock',
          subtext: 'cooldown · file · slot',
          external: 'ravendb',
        },
      },
    ],
  },
  {
    id: 'runbook',
    label: 'Reference runbook',
    rows: [
      {
        type: 'step',
        node: {
          id: 'load_account_bundle',
          label: 'Account bundle',
          subtext: 'profile + metrics',
        },
      },
      {
        type: 'step',
        node: {
          id: 'fetch_search_references',
          label: 'Search fetch',
          subtext: '1 query / niche',
          external: 'x_api',
        },
      },
      {
        type: 'step',
        node: {
          id: 'collect_external_references',
          label: 'Collect references',
          subtext: 'build + dedupe pool',
        },
      },
      {
        type: 'step',
        node: {
          id: 'fetch_own_post_history',
          label: 'Own posts',
          subtext: 'engagement history',
          external: 'x_api',
        },
      },
      {
        type: 'parallel',
        id: 'summarize_for_compose',
        label: 'summarize_for_compose',
        note: 'parallel branches · executed sequentially (A then B)',
        branches: [
          {
            id: 'analyze_external_references',
            label: 'analyze_external',
            steps: [
              {
                id: 'summarize_for_compose.analyze_external_references.rank_external_references',
                label: 'Rank external',
                subtext: 'engagement score',
              },
              {
                id: 'summarize_for_compose.analyze_external_references.brief_external_references',
                label: 'Brief external',
                subtext: 'LLM pattern summary',
                external: 'claude',
              },
            ],
          },
          {
            id: 'analyze_own_posts',
            label: 'analyze_own',
            steps: [
              {
                id: 'summarize_for_compose.analyze_own_posts.rank_own_posts',
                label: 'Rank own posts',
                subtext: 'voice signals',
              },
              {
                id: 'summarize_for_compose.analyze_own_posts.brief_own_posts',
                label: 'Brief own posts',
                subtext: 'LLM voice brief',
                external: 'claude',
              },
            ],
          },
        ],
      },
    ],
  },
  {
    id: 'orchestrator-post',
    rows: [
      {
        type: 'step',
        node: {
          id: 'compose_until_safe',
          label: 'Compose',
          subtext: 'compose · safety · regen loop',
          external: 'claude',
        },
      },
      {
        type: 'step',
        node: { id: 'publish_post', label: 'Publish', subtext: 'post to X', external: 'x_api' },
      },
      {
        type: 'step',
        node: {
          id: 'complete',
          label: 'Complete',
          subtext: 'tracked post saved',
          external: 'ravendb',
        },
      },
    ],
  },
];

/** Flattened step nodes (for the reducer + initial state). */
export const PIPELINE_FLOW_STEP_NODES: FlowNodeDef[] = PIPELINE_FLOW.flatMap((section) =>
  section.rows.flatMap((row) =>
    row.type === 'step' ? [row.node] : row.branches.flatMap((b) => b.steps)
  )
);

export const PIPELINE_FLOW_STEP_IDS = PIPELINE_FLOW_STEP_NODES.map((n) => n.id);

/**
 * Flatten the step-node ids from any FlowSection[] (e.g. one derived from a
 * per-account spec via `flowFromSpec`). Used to seed/filter the live-run reducer
 * so progress events light up exactly the nodes that are rendered.
 */
export function sectionStepIds(sections: FlowSection[]): string[] {
  return sections.flatMap((section) =>
    section.rows.flatMap((row) =>
      row.type === 'step' ? [row.node.id] : row.branches.flatMap((b) => b.steps.map((s) => s.id))
    )
  );
}
