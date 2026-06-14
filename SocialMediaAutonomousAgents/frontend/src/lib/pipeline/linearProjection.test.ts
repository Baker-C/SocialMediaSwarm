import { toLinearStepId } from './linearProjection';

describe('linearProjection', () => {
  it('passes orchestrator ids through unchanged', () => {
    expect(toLinearStepId('compose')).toBe('compose');
    expect(toLinearStepId('publish')).toBe('publish');
  });

  it('maps runbook timeline fetch to fetch_timeline', () => {
    expect(toLinearStepId('fetch_external_references.fetch_timeline_references')).toBe(
      'fetch_timeline'
    );
  });

  it('maps runbook rank step to rank_references', () => {
    expect(
      toLinearStepId('summarize_for_compose.analyze_external_references.rank_external_references')
    ).toBe('rank_references');
  });
});
