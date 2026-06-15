import { useParams } from 'react-router-dom';
import { useMemo, useState } from 'react';
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
import type { ContrastPattern, PunctuationRule } from '../../types';
import type { VoiceRevision } from '../../types';

// A soul source can be either the live /edit payload or an archived revision.
type SoulSource = {
  personality?: string;
  posting_prompt?: string;
  contrast_patterns?: ContrastPattern[];
  punctuation_rules?: PunctuationRule[];
  // legacy fallbacks for old revisions:
  system_prompt?: string;
  negative_semantics?: string[];
};

function hasStoredSoul(s: SoulSource | null | undefined): boolean {
  if (!s) return false;
  return Boolean(
    s.personality?.trim() ||
      s.posting_prompt?.trim() ||
      s.system_prompt?.trim() ||
      (s.contrast_patterns && s.contrast_patterns.length) ||
      (s.punctuation_rules && s.punctuation_rules.length) ||
      (s.negative_semantics && s.negative_semantics.length)
  );
}

// Reusable soul renderer. Handles legacy fallbacks so old revisions still display.
function SoulDetail({ soul }: { soul: SoulSource }) {
  const posting = soul.posting_prompt?.trim() || soul.system_prompt?.trim() || '';
  const contrast: ContrastPattern[] =
    soul.contrast_patterns ??
    (soul.negative_semantics ?? []).map((t) => ({ text: t, correlation: 'negative' as const }));
  const punctuation = soul.punctuation_rules ?? [];

  return (
    <>
      {soul.personality?.trim() && (
        <div className="voice-expand__block">
          <span className="voice-expand__label">Personality</span>
          <p className="voice-expand__text" style={{ whiteSpace: 'pre-wrap' }}>
            {soul.personality}
          </p>
        </div>
      )}
      <div className="voice-expand__block">
        <span className="voice-expand__label">Posting prompt</span>
        <p className="voice-expand__text" style={{ whiteSpace: 'pre-wrap' }}>
          {posting || '—'}
        </p>
      </div>
      {contrast.length > 0 && (
        <div className="voice-expand__block">
          <span className="voice-expand__label">Contrast patterns</span>
          <ul className="voice-expand__list">
            {contrast.map((p) => (
              <li key={p.text}>
                <span className={p.correlation === 'negative' ? 'text-red-400' : 'text-green-400'}>
                  [{p.correlation}]
                </span>{' '}
                {p.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {punctuation.length > 0 && (
        <div className="voice-expand__block">
          <span className="voice-expand__label">Punctuation rules</span>
          <ul className="voice-expand__list">
            {punctuation.map((r) => (
              <li key={r.pattern} className="font-mono text-xs">
                {r.pattern}
                {r.replacement != null ? ` → ${r.replacement}` : ' → (remove)'}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

// Soul section — shows the version selected in the dropdown. The current version is
// fed by the /edit payload (useAccountVoice); a previous version is its archived revision.
function CurrentSoulSection({
  soul,
  isLoading,
  headerLabel,
  versionLabel,
  versionSeq,
  versionHash,
}: {
  soul: SoulSource | undefined;
  isLoading: boolean;
  headerLabel: string;
  versionLabel?: string | null;
  versionSeq?: number | null;
  versionHash?: string | null;
}) {
  return (
    <section className="hq-panel" aria-label="Soul">
      <div className="hq-panel__header">
        <h3 className="hq-panel__title">{headerLabel}</h3>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-1 bg-orange-900/30 text-orange-400 rounded">
            {versionLabel || 'v1'}
          </span>
          {versionSeq != null && (
            <span className="text-xs px-2 py-1 bg-gray-800 text-gray-400 rounded">
              seq #{versionSeq}
            </span>
          )}
          {versionHash && (
            <span
              className="text-xs px-2 py-1 bg-gray-800 text-gray-400 rounded font-mono cursor-help"
              title={versionHash}
            >
              {versionHash.slice(0, 12)}…
            </span>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="App-loading">Loading soul…</p>
      ) : hasStoredSoul(soul) ? (
        <div className="space-y-6">
          <SoulDetail soul={soul as SoulSource} />
        </div>
      ) : (
        <p className="page-hint">No soul configuration set.</p>
      )}
    </section>
  );
}

export function VoiceExperimentsPage() {
  const { accountId } = useParams();
  const accountQuery = useAccount(accountId);
  const voiceQuery = useAccountVoice(accountId);
  const revisionsQuery = useVoiceRevisions(accountId);
  const postsQuery = useTrackedPosts(accountId);

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

  const voice = voiceQuery.data;
  const currentSeq = voice?.voice_version_seq ?? accountQuery.data?.voice_version_seq ?? null;
  const currentLabel =
    voice?.voice_version_label ?? accountQuery.data?.voice_version_label ?? 'v1';
  const revisions: VoiceRevision[] = revisionsQuery.data?.revisions ?? [];

  // Version dropdown options: every recorded version, newest first. Ensure the current
  // version is present even if it somehow lacks a revision row.
  const versionOptions = useMemo(() => {
    const bySeq = new Map<number, { seq: number; label: string }>();
    for (const r of revisions) {
      if (r.seq != null) bySeq.set(r.seq, { seq: r.seq, label: r.label });
    }
    if (currentSeq != null && !bySeq.has(currentSeq)) {
      bySeq.set(currentSeq, { seq: currentSeq, label: currentLabel });
    }
    return Array.from(bySeq.values()).sort((a, b) => b.seq - a.seq);
  }, [revisions, currentSeq, currentLabel]);

  // null selection = follow current; otherwise show the chosen version's snapshot.
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const effectiveSeq = selectedSeq ?? currentSeq;
  const isCurrentSelected = effectiveSeq === currentSeq;
  const selectedRevision = revisions.find((r) => r.seq === effectiveSeq);

  const displayedSoul: SoulSource | undefined = isCurrentSelected
    ? (voice as SoulSource | undefined)
    : (selectedRevision as SoulSource | undefined);
  const displayedLabel = isCurrentSelected
    ? currentLabel
    : selectedRevision?.label ?? `v${effectiveSeq ?? ''}`;
  const displayedSeq = isCurrentSelected ? currentSeq : selectedRevision?.seq ?? effectiveSeq;
  const displayedHash = isCurrentSelected
    ? voice?.voice_version_hash
    : selectedRevision?.version_hash;
  const soulHeaderLabel = isCurrentSelected
    ? 'Current soul'
    : `Soul — ${displayedLabel} (previous)`;

  const renderVoiceExpanded = (row: VoiceVersionStats) => {
    const revision = revisions.find((r) => r.seq === row.seq);
    const isCurrent = row.seq != null && row.seq === currentSeq;
    const storedVoice = revision && hasStoredSoul(revision) ? revision : null;

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

        {storedVoice ? (
          <SoulDetail soul={storedVoice} />
        ) : (
          <p className="page-hint">
            Prompt text was not recorded for this revision. Only revisions saved after the voice
            archive update include full prompt details.
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="page-content">
      <div
        className="page-header__actions page-content__toolbar"
        style={{ display: 'flex', justifyContent: 'flex-end' }}
      >
        <select
          className="voice-badge"
          aria-label="Select soul version"
          value={effectiveSeq ?? ''}
          onChange={(e) =>
            setSelectedSeq(e.target.value === '' ? null : Number(e.target.value))
          }
        >
          {versionOptions.map((o) => (
            <option key={o.seq} value={o.seq}>
              {o.label} {o.seq === currentSeq ? '(current)' : '(previous)'}
            </option>
          ))}
        </select>
      </div>

      <CurrentSoulSection
        soul={displayedSoul}
        isLoading={isCurrentSelected ? voiceQuery.isLoading : revisionsQuery.isLoading}
        headerLabel={soulHeaderLabel}
        versionLabel={displayedLabel}
        versionSeq={displayedSeq}
        versionHash={displayedHash}
      />

      <section className="hq-panel" aria-label="Revision timeline">
        <h3 className="hq-panel__title">Revision timeline</h3>
        {revisionsQuery.isLoading ? (
          <p className="App-loading">Loading revisions…</p>
        ) : timeline.length === 0 ? (
          <p className="page-hint">No voice revisions recorded.</p>
        ) : (
          <ol className="revision-timeline">
            {timeline.map((r) => {
              const revision = revisions.find((item) => item.seq === r.seq);
              const hasPrompt = revision && hasStoredSoul(revision);
              return (
                <li key={r.seq} className="revision-timeline__item">
                  <div className="revision-timeline__row">
                    <span className="revision-timeline__seq">#{r.seq}</span>
                    <span className="revision-timeline__label">{r.label}</span>
                    <span className="revision-timeline__date">{formatShortDate(r.changed_at)}</span>
                  </div>
                  {hasPrompt ? (
                    <details className="revision-timeline__voice">
                      <summary>Voice prompt</summary>
                      <div className="voice-expand voice-expand--inline">
                        <SoulDetail soul={revision} />
                      </div>
                    </details>
                  ) : null}
                </li>
              );
            })}
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
