import { Link, useParams } from 'react-router-dom';
import { useMemo } from 'react';
import { compareVoiceVersions, revisionTimeline } from '../../analytics/selectors/voiceComparison';
import { normalizeTrackedPosts } from '../../analytics/normalize/trackedPost';
import { buildCorrelationPoints } from '../../analytics/selectors/engagementCurves';
import { CorrelationScatter } from '../../components/charts/CorrelationScatter';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { TablePanelHeader } from '../../components/data/TablePanelHeader';
import { useAccount } from '../../hooks/queries/useAccounts';
import { useAccountVoice } from '../../hooks/queries/useAccountVoice';
import { useTrackedPosts } from '../../hooks/queries/useTrackedPosts';
import { useVoiceRevisions } from '../../hooks/queries/useVoiceRevisions';
import { formatPercent, formatShortDate } from '../../lib/format';
import type { VoiceVersionStats } from '../../analytics/selectors/voiceComparison';
import type { VoiceRevision } from '../../types';

export function VoiceExperimentsPage() {
  const { accountId } = useParams();
  const accountQuery = useAccount(accountId);
  const revisionsQuery = useVoiceRevisions(accountId);
  const postsQuery = useTrackedPosts(accountId);
  const voiceQuery = useAccountVoice(accountId);

  const posts = useMemo(
    () => normalizeTrackedPosts(postsQuery.data?.posts ?? []),
    [postsQuery.data]
  );

  const comparison = useMemo(
    () => compareVoiceVersions(posts, revisionsQuery.data?.revisions ?? []),
    [posts, revisionsQuery.data]
  );

  const timeline = revisionTimeline(revisionsQuery.data?.revisions ?? []);
  const correlationPoints = useMemo(() => buildCorrelationPoints(posts), [posts]);

  const comparisonColumns: DataTableColumn<VoiceVersionStats>[] = [
    { id: 'label', header: 'Voice', accessor: (r) => r.label, sortValue: (r) => r.label },
    {
      id: 'seq',
      header: 'Seq',
      accessor: (r) => r.seq ?? '—',
      sortValue: (r) => r.seq ?? -1,
      align: 'right',
    },
    {
      id: 'posts',
      header: 'Posts',
      accessor: (r) => r.postCount,
      sortValue: (r) => r.postCount,
      align: 'right',
    },
    {
      id: 'er',
      header: 'Avg ER',
      accessor: (r) => formatPercent(r.avgEr, 2),
      sortValue: (r) => r.avgEr ?? -1,
      align: 'right',
    },
    {
      id: 'imp',
      header: 'Avg impressions',
      accessor: (r) =>
        r.avgImpressions != null ? Math.round(r.avgImpressions).toLocaleString() : '—',
      sortValue: (r) => r.avgImpressions ?? -1,
      align: 'right',
    },
  ];

  const currentVoice = accountQuery.data?.voice_version_label ?? 'default';
  const currentSeq = accountQuery.data?.voice_version_seq ?? null;
  const revisions: VoiceRevision[] = revisionsQuery.data?.revisions ?? [];

  const renderVoiceExpanded = (row: VoiceVersionStats) => {
    const revision = revisions.find((r) => r.seq === row.seq);
    const isCurrent = row.seq != null && row.seq === currentSeq;
    const voice = voiceQuery.data;

    return (
      <div className="voice-expand">
        <div className="voice-expand__meta">
          <span className="voice-expand__tag">
            Voice {row.label}
            {row.seq != null ? ` (#${row.seq})` : ''}
          </span>
          {revision ? (
            <span className="voice-expand__tag">Changed {formatShortDate(revision.changed_at)}</span>
          ) : null}
          {revision ? (
            <span className="voice-expand__hash" title={revision.version_hash}>
              Hash {revision.version_hash.slice(0, 16)}…
            </span>
          ) : null}
          {isCurrent ? <span className="voice-expand__current">Active</span> : null}
        </div>

        {isCurrent ? (
          voiceQuery.isLoading ? (
            <p className="App-loading">Loading voice…</p>
          ) : voice ? (
            <>
              <div className="voice-expand__block">
                <span className="voice-expand__label">System prompt</span>
                <p className="voice-expand__text">{voice.system_prompt || '—'}</p>
              </div>
              {voice.personality ? (
                <div className="voice-expand__block">
                  <span className="voice-expand__label">Personality</span>
                  <p className="voice-expand__text">{voice.personality}</p>
                </div>
              ) : null}
              {voice.negative_semantics && voice.negative_semantics.length > 0 ? (
                <div className="voice-expand__block">
                  <span className="voice-expand__label">Negative semantics</span>
                  <ul className="voice-expand__list">
                    {voice.negative_semantics.map((item: string) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="page-hint">Could not load the active voice details.</p>
          )
        ) : (
          <p className="page-hint">
            Prompt text is only stored for the active voice. Previous revisions are identified by
            version hash only.
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="page-content">
      <div className="page-header__actions page-content__toolbar">
        <Link to={`/accounts/${accountId}/settings`} className="voice-badge">
          Current: {currentVoice}
        </Link>
      </div>

      <section className="hq-panel" aria-label="Revision timeline">
        <h3 className="hq-panel__title">Revision timeline</h3>
        {revisionsQuery.isLoading ? (
          <p className="App-loading">Loading revisions…</p>
        ) : timeline.length === 0 ? (
          <p className="page-hint">No voice revisions recorded.</p>
        ) : (
          <ol className="revision-timeline">
            {timeline.map((r) => (
              <li key={r.seq} className="revision-timeline__item">
                <span className="revision-timeline__seq">#{r.seq}</span>
                <span className="revision-timeline__label">{r.label}</span>
                <span className="revision-timeline__date">{formatShortDate(r.changed_at)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="hq-panel" aria-label="Voice comparison">
        <TablePanelHeader title="Performance by voice version" tableId="voice-comparison" />
        <DataTable
          columns={comparisonColumns}
          rows={comparison}
          rowKey={(r) => String(r.seq ?? r.label)}
          emptyMessage="No voice comparison data."
          ariaLabel="Voice version comparison"
          renderExpanded={renderVoiceExpanded}
        />
      </section>

      <CorrelationScatter points={correlationPoints} />
    </div>
  );
}
