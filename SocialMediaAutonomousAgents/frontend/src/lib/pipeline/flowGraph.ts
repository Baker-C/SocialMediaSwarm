/* ────────────────────────────────────────────────────────────────────────────
 * Flow-diagram types shared by the pipeline views.
 *
 * The diagram is built per-account from the live PipelineSpec via `flowFromSpec`
 * (lib/pipeline/specToFlow.ts) — there is no hardcoded mirror of the backend
 * runbook. Each node `id` equals the emitted progress `step_id` (the dotted id
 * from `flatten_steps`), so nodes light up during a live run.
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

/**
 * Flatten the step-node ids from a FlowSection[] (derived from a per-account
 * spec via `flowFromSpec`). Used to seed/filter the live-run reducer so progress
 * events light up exactly the nodes that are rendered.
 */
export function sectionStepIds(sections: FlowSection[]): string[] {
  return sections.flatMap((section) =>
    section.rows.flatMap((row) =>
      row.type === 'step' ? [row.node.id] : row.branches.flatMap((b) => b.steps.map((s) => s.id))
    )
  );
}
