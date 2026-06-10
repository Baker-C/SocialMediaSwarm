import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { PHASE_LABELS, STATUS_LABELS } from '../../analytics/constants';
import {
  opsHighlights,
  phaseHealth,
  skipReasonPareto,
} from '../../analytics/selectors/pipelineOps';
import { defaultSinceDays } from '../../lib/urlFilters';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { PageHeader } from '../../components/layout/PageHeader';
import {
  useFleetPipelineOutcomes,
  usePipelineOutcomes,
} from '../../hooks/queries/usePipelineOutcomes';
import type { PipelineOutcome } from '../../types';
import { formatShortDate } from '../../lib/format';
import { SkipReasonChart } from './SkipReasonChart';

type PipelineOpsBodyProps = {
  accountId?: string;
  title: string;
  subtitle: string;
};

function PipelineOpsBody({ accountId, title, subtitle }: PipelineOpsBodyProps) {
  const filters = useMemo(
    () => ({ since: defaultSinceDays(7), limit: 200 }),
    []
  );

  const accountQuery = usePipelineOutcomes(accountId, filters);
  const fleetQuery = useFleetPipelineOutcomes(filters);
  const outcomesQuery = accountId ? accountQuery : fleetQuery;

  const outcomes = outcomesQuery.data?.outcomes ?? [];
  const skipRows = skipReasonPareto(outcomes);
  const phases = phaseHealth(outcomes);
  const highlights = opsHighlights(outcomes);

  const columns: DataTableColumn<PipelineOutcome>[] = [
    {
      id: 'time',
      header: 'Time',
      accessor: (o) => formatShortDate(o.created_at),
      sortValue: (o) => o.created_at,
    },
    ...(accountId
      ? []
      : [
          {
            id: 'account',
            header: 'Account',
            accessor: (o: PipelineOutcome) => o.account_id,
            sortValue: (o: PipelineOutcome) => o.account_id,
          } as DataTableColumn<PipelineOutcome>,
        ]),
    {
      id: 'phase',
      header: 'Phase',
      accessor: (o) => PHASE_LABELS[o.phase] ?? o.phase,
      sortValue: (o) => o.phase,
    },
    {
      id: 'status',
      header: 'Status',
      accessor: (o) => STATUS_LABELS[o.status] ?? o.status,
      sortValue: (o) => o.status,
    },
    {
      id: 'reason',
      header: 'Reason',
      accessor: (o) => o.reason ?? '—',
      sortValue: (o) => o.reason ?? '',
    },
  ];

  return (
    <div className="page-content">
      <PageHeader title={title} subtitle={subtitle} />

      {highlights.length > 0 ? (
        <div className="ops-alerts" role="status">
          <h3 className="ops-alerts__title">Ops highlights</h3>
          <ul className="ops-alerts__list">
            {highlights.slice(0, 8).map((o) => (
              <li key={`${o.account_id}-${o.created_at}-${o.phase}`} className="ops-alerts__item">
                {o.account_id}: {o.phase} · {o.status} · {o.reason ?? '(none)'}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="hq-grid">
        <section className="hq-panel" aria-label="Skip reasons">
          <h3 className="hq-panel__title">Skip / reject reasons</h3>
          <SkipReasonChart rows={skipRows} />
        </section>
        <section className="hq-panel" aria-label="Phase health">
          <h3 className="hq-panel__title">Phase health (7d)</h3>
          <DataTable
            columns={[
              {
                id: 'phase',
                header: 'Phase',
                accessor: (r) => PHASE_LABELS[r.phase] ?? r.phase,
              },
              { id: 'total', header: 'Total', accessor: (r) => r.total, align: 'right' },
              { id: 'success', header: 'Success', accessor: (r) => r.success, align: 'right' },
              {
                id: 'rate',
                header: 'Success rate',
                accessor: (r) => `${(r.successRate * 100).toFixed(1)}%`,
                align: 'right',
              },
            ]}
            rows={phases}
            rowKey={(r) => r.phase}
            emptyMessage="No outcomes."
            ariaLabel="Phase health"
          />
        </section>
      </div>

      {outcomesQuery.isLoading ? <p className="App-loading">Loading pipeline outcomes…</p> : null}
      {!outcomesQuery.isLoading ? (
        <section className="hq-panel" aria-label="Outcomes timeline">
          <h3 className="hq-panel__title">Outcomes</h3>
          <DataTable
            columns={columns}
            rows={outcomes}
            rowKey={(o) => `${o.account_id}-${o.created_at}-${o.phase}`}
            emptyMessage="No pipeline outcomes in window."
            ariaLabel="Pipeline outcomes"
          />
        </section>
      ) : null}
    </div>
  );
}

export function PipelineOpsPage() {
  const { accountId } = useParams();
  return (
    <PipelineOpsBody
      accountId={accountId}
      title="Pipeline Ops"
      subtitle="Outcomes, skips, and phase health"
    />
  );
}

export function FleetPipelinePage() {
  return (
    <PipelineOpsBody
      title="Fleet Pipeline"
      subtitle="Outcomes across all accounts (7d)"
    />
  );
}
