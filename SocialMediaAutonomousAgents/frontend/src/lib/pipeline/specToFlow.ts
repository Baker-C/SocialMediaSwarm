import type { FlowSection, FlowNodeDef, FlowExternal } from './flowGraph';
import type { PipelineSpec, SpecNode } from '../../types/domain/pipelineSpec';
import { isComposite } from '../../types/domain/pipelineSpec';

// Tool ids verified: doc 03 §3 (the 6 SENSE tools) + doc 06 §5 (the 2 ACT tools).
// Longest-prefix-first so 'data.publish_post' is matched before any shorter 'data.' rule.
const EXTERNAL_BY_TOOL_PREFIX: Array<[string, FlowExternal]> = [
  ['data.search_fetch', 'x_api'],       // doc 03: search_fetch.TOOL_SOURCE = x_search/x_api
  ['data.account_profile', 'x_api'],    // doc 03: account_profile reads the X profile
  ['data.own_posts_fetch', 'ravendb'],  // doc 03: own posts come from RavenDB, not X
  ['data.publish_post', 'x_api'],       // doc 06 §5.2: publish_post.TOOL_SOURCE = "x_api"
  ['llm.', 'claude'],                   // doc 06 §5.1: compose_until_safe is llm.* → claude
];

// `_internal.collect_external` (doc 04 §7 sentinel) and `deterministic.*` rankers have
// no external call-out (in-process) — externalFor returns undefined for them.
function externalFor(toolId: string): FlowExternal | undefined {
  const hit = EXTERNAL_BY_TOOL_PREFIX.find(([p]) => toolId.startsWith(p));
  return hit?.[1];
}

function dottedId(node: SpecNode, prefix: string): string {
  return prefix ? `${prefix}.${node.id}` : node.id;
}

function humanize(id: string): string {
  return id
    .replace(/_/g, ' ')
    .split(' ')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function leafNode(step: Extract<SpecNode, { kind: 'step' }>, prefix: string): FlowNodeDef {
  return {
    id: dottedId(step, prefix),         // matches flatten_steps + emitted progress step_id
    label: humanize(step.id),
    subtext: step.purpose?.slice(0, 48),
    external: externalFor(step.tool_id),
  };
}

// Recursive walk of nested spec to build the flow. Called once per spec.steps[] item.
function walkNode(node: SpecNode, prefix: string): { rows: any[]; stepIds: string[] } {
  if (node.kind === 'step') {
    const leaf = leafNode(node, prefix);
    return {
      rows: [{ type: 'step', node: leaf }],
      stepIds: [leaf.id],
    };
  }

  // Composite (parallel or chain)
  const fullId = dottedId(node, prefix);
  const newPrefix = fullId;

  if (node.kind === 'chain') {
    // A chain at top level: its children become sequential step rows (no composite row).
    const childResults = node.children.map(child => walkNode(child, newPrefix));
    return {
      rows: childResults.flatMap(r => r.rows),
      stepIds: childResults.flatMap(r => r.stepIds),
    };
  }

  // parallel: create a parallel row with branches
  const branches = node.children
    .filter(c => c.kind !== 'parallel') // sanity: no nested parallels
    .map((child) => {
      if (isComposite(child) && child.kind === 'chain') {
        // A chain inside parallel becomes a branch with sequential steps
        const branchPrefix = dottedId(child, newPrefix);
        const childResults = child.children.map(grandchild =>
          walkNode(grandchild, branchPrefix)
        );
        return {
          id: child.id,
          label: humanize(child.id),
          steps: childResults.flatMap(r => {
            // Flatten step rows from the chain children
            const steps: any[] = [];
            r.rows.forEach(row => {
              if (row.type === 'step') {
                steps.push(row.node);
              }
            });
            return steps;
          }),
          stepIds: childResults.flatMap(r => r.stepIds),
        };
      } else if (child.kind === 'step') {
        // A step inside parallel: single-step branch
        const leaf = leafNode(child, newPrefix);
        return {
          id: child.id,
          label: humanize(child.id),
          steps: [leaf],
          stepIds: [leaf.id],
        };
      }
      // Should not reach here (no nested parallel)
      return { id: '', label: '', steps: [], stepIds: [] };
    });

  const allStepIds = branches.flatMap(b => b.stepIds);
  const cleanBranches = branches.map(({ stepIds, ...b }) => b);

  return {
    rows: [
      {
        type: 'parallel' as const,
        id: fullId,
        label: humanize(node.id),
        note: 'parallel branches · executed sequentially (A then B)',
        branches: cleanBranches,
      },
    ],
    stepIds: allStepIds,
  };
}

// The 3 imperative lock stages (retained as a small constant because those stages
// are NOT in the spec — doc 07 §2.2 keeps locks imperative) and they still emit
// progress events. This is the one honest piece of hand-maintenance left.
const OPS_PRE_SECTION: FlowSection = {
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
};

/**
 * Transform a PipelineSpec into FlowSection[] for rendering.
 * Walks the nested spec.steps and derives the same shape as the current hardcoded PIPELINE_FLOW.
 */
export function flowFromSpec(spec: PipelineSpec): FlowSection[] {
  const specRows: any[] = [];
  const allStepIds: string[] = [];

  // Walk each top-level spec node
  for (const node of spec.steps) {
    const result = walkNode(node, '');
    specRows.push(...result.rows);
    allStepIds.push(...result.stepIds);
  }

  return [
    OPS_PRE_SECTION,
    {
      id: 'runbook',
      label: 'Reference runbook',
      rows: specRows,
    },
  ];
}

/**
 * Extract the flattened list of dotted step ids from the spec.
 * MUST match the backend's flatten_steps() output exactly.
 * Used by the reducer to initialize the known-id set.
 */
export function flowStepIds(spec: PipelineSpec): string[] {
  const ids: string[] = [];

  function walk(node: SpecNode, prefix: string) {
    const fullId = dottedId(node, prefix);
    if (node.kind === 'step') {
      ids.push(fullId);
    } else if (node.kind === 'chain') {
      // Chain doesn't emit its own step, only children
      for (const child of node.children) {
        walk(child, fullId);
      }
    } else if (node.kind === 'parallel') {
      // Parallel doesn't emit its own step, only children
      for (const child of node.children) {
        walk(child, fullId);
      }
    }
  }

  for (const node of spec.steps) {
    walk(node, '');
  }

  return ids;
}
