import { applyFlowProgress, initialFlowState } from './flowReducer';

// Mirrors a per-account spec's flattened step ids (sectionStepIds): the imperative
// wrappers plus the SENSE+ACT leaves, including the new ACT tail.
const STEP_IDS = [
  'load_account',
  'post_lock',
  'load_account_bundle',
  'summarize_for_compose.analyze_external_references.rank_external_references',
  'summarize_for_compose.analyze_external_references.brief_external_references',
  'compose_until_safe',
  'publish_post',
];
const VALID_IDS = new Set(STEP_IDS);

describe('flowReducer', () => {
  it('seeds every known step as pending', () => {
    const state = initialFlowState(STEP_IDS);
    expect(state.load_account).toBe('pending');
    expect(state.compose_until_safe).toBe('pending');
  });

  it('marks a known step active then done', () => {
    let state = initialFlowState(STEP_IDS);
    state = applyFlowProgress(
      state,
      { step_id: 'load_account', label: 'Loading account', status: 'active', scope: 'orchestrator' },
      VALID_IDS
    );
    expect(state.load_account).toBe('active');
    state = applyFlowProgress(
      state,
      { step_id: 'load_account', label: 'Loading account', status: 'done', scope: 'orchestrator' },
      VALID_IDS
    );
    expect(state.load_account).toBe('done');
  });

  it('lights up the new ACT-tail steps from the spec', () => {
    let state = initialFlowState(STEP_IDS);
    state = applyFlowProgress(
      state,
      { step_id: 'compose_until_safe', label: 'Compose', status: 'active', scope: 'runbook' },
      VALID_IDS
    );
    state = applyFlowProgress(
      state,
      { step_id: 'publish_post', label: 'Publish', status: 'done', scope: 'runbook' },
      VALID_IDS
    );
    expect(state.compose_until_safe).toBe('active');
    expect(state.publish_post).toBe('done');
  });

  it('allows parallel branch steps to be active together', () => {
    let state = initialFlowState(STEP_IDS);
    state = applyFlowProgress(
      state,
      {
        step_id: 'summarize_for_compose.analyze_external_references.rank_external_references',
        label: 'Rank external',
        status: 'active',
        scope: 'runbook',
      },
      VALID_IDS
    );
    state = applyFlowProgress(
      state,
      {
        step_id: 'summarize_for_compose.analyze_external_references.brief_external_references',
        label: 'Brief external',
        status: 'active',
        scope: 'runbook',
      },
      VALID_IDS
    );
    expect(state['summarize_for_compose.analyze_external_references.rank_external_references']).toBe('active');
    expect(state['summarize_for_compose.analyze_external_references.brief_external_references']).toBe('active');
  });

  it('ignores progress for ids outside the spec set', () => {
    let state = initialFlowState(STEP_IDS);
    state = applyFlowProgress(
      state,
      { step_id: 'compose', label: 'Compose', status: 'active', scope: 'orchestrator' },
      VALID_IDS
    );
    expect(state.compose).toBeUndefined();
  });
});
