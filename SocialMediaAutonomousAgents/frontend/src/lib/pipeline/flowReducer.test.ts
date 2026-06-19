import { applyFlowProgress, initialFlowState } from './flowReducer';

describe('flowReducer', () => {
  it('marks a known orchestrator step active and done', () => {
    let state = initialFlowState();
    state = applyFlowProgress(state, {
      step_id: 'load_account',
      label: 'Loading account',
      status: 'active',
      scope: 'orchestrator',
    });
    expect(state.load_account).toBe('active');
    state = applyFlowProgress(state, {
      step_id: 'load_account',
      label: 'Loading account',
      status: 'done',
      scope: 'orchestrator',
    });
    expect(state.load_account).toBe('done');
  });

  it('allows parallel runbook fetches to be active together', () => {
    let state = initialFlowState();
    state = applyFlowProgress(state, {
      step_id: 'fetch_external_references.fetch_timeline_references',
      label: 'Timeline',
      status: 'active',
      scope: 'runbook',
    });
    state = applyFlowProgress(state, {
      step_id: 'fetch_external_references.fetch_search_references',
      label: 'Search',
      status: 'active',
      scope: 'runbook',
    });
    expect(state['fetch_external_references.fetch_timeline_references']).toBe('active');
    expect(state['fetch_external_references.fetch_search_references']).toBe('active');
  });

  it('highlights claude satellite while brief step is active', () => {
    let state = initialFlowState();
    state = applyFlowProgress(state, {
      step_id: 'summarize_for_compose.analyze_external_references.brief_external_references',
      label: 'Brief external',
      status: 'active',
      scope: 'runbook',
    });
    expect(state.claude).toBe('active');
  });

  it('lights up spec-derived step ids when given a custom valid-id set', () => {
    // A per-account spec drives the live view: the ACT tail uses compose_until_safe
    // / publish_post, which are NOT in the static default set.
    const validIds = new Set(['compose_until_safe', 'publish_post']);
    let state = initialFlowState(['compose_until_safe', 'publish_post']);

    state = applyFlowProgress(
      state,
      { step_id: 'compose_until_safe', label: 'Compose', status: 'active', scope: 'runbook' },
      validIds
    );
    expect(state.compose_until_safe).toBe('active');

    // An id outside the spec's set is ignored.
    state = applyFlowProgress(
      state,
      { step_id: 'compose', label: 'Compose', status: 'done', scope: 'orchestrator' },
      validIds
    );
    expect(state.compose).toBeUndefined();
  });
});
