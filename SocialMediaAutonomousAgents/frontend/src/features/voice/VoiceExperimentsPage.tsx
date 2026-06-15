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
import type { AccountVoiceDetail } from '../../types';
import type { VoiceRevision } from '../../types';

// Voice polish rules reference
const VOICE_POLISH_RULES = {
  bannedPhrases: [
    { pattern: 'as an AI', replace: '' },
    { pattern: 'as a language model', replace: '' },
    { pattern: 'I hope this helps', replace: '' },
    { pattern: 'in conclusion', replace: '' },
    { pattern: 'to summarize', replace: '' },
    { pattern: 'in summary', replace: '' },
    { pattern: 'furthermore', replace: '' },
    { pattern: 'moreover', replace: '' },
    { pattern: 'let that sink in', replace: '' },
    { pattern: 'deep dive', replace: '' },
    { pattern: 'at its core', replace: '' },
    { pattern: 'paradigm shift', replace: 'shift' },
    { pattern: 'game-changer', replace: 'big deal' },
    { pattern: 'utilize', replace: 'use' },
    { pattern: 'leverage', replace: 'use' },
    { pattern: 'robust', replace: 'solid' },
    { pattern: 'stakeholders', replace: 'people' },
    { pattern: 'ecosystem', replace: 'world' },
    { pattern: 'navigate the', replace: 'handle the' },
    { pattern: 'shed light on', replace: 'show' },
    { pattern: 'inflection point', replace: 'turning point' },
  ],
  contrastPatterns: [
    "It's not X, it's Y",
    'The real issue isn\'t ... it\'s ...',
    'This isn\'t about X, it\'s about Y',
    'Don\'t think of it as ... think of it as ...',
    'Less about X ... more about Y',
  ],
  punctuationRules: [
    'No em dashes (—) — use commas or periods instead',
    'No double hyphens (--) — use commas or periods',
    'Fix multiple spaces',
    'Remove space before punctuation',
  ],
  textRules: [
    '30% chance to lowercase first letter of sentences (casual tone)',
  ],
};

type VoicePromptSource = Pick<
  VoiceRevision,
  'system_prompt' | 'personality' | 'negative_semantics'
> &
  Partial<Pick<AccountVoiceDetail, 'system_prompt' | 'personality' | 'negative_semantics'>>;

function hasStoredVoiceText(source: VoicePromptSource | null | undefined): boolean {
  if (!source) return false;
  return Boolean(
    (source.system_prompt && source.system_prompt.trim()) ||
      (source.personality && source.personality.trim()) ||
      (source.negative_semantics && source.negative_semantics.length > 0)
  );
}

function VoicePromptDetail({ voice }: { voice: VoicePromptSource }) {
  return (
    <>
      <div className="voice-expand__block">
        <span className="voice-expand__label">System prompt</span>
        <p className="voice-expand__text">{voice.system_prompt?.trim() || '—'}</p>
      </div>
      {voice.personality?.trim() ? (
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
  );
}

function CurrentVoiceSection({
  account,
  voice,
  revision,
  isLoading,
}: {
  account: any;
  voice: AccountVoiceDetail | undefined;
  revision: VoiceRevision | undefined;
  isLoading: boolean;
}) {
  const systemPrompt = revision?.system_prompt || voice?.system_prompt || account?.system_prompt || '';
  const personality = revision?.personality || voice?.personality || account?.personality || '';
  const negSemantics = revision?.negative_semantics || voice?.negative_semantics || account?.negative_semantics || [];

  return (
    <section className="hq-panel" aria-label="Current voice">
      <div className="hq-panel__header">
        <h3 className="hq-panel__title">Current voice</h3>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-1 bg-orange-900/30 text-orange-400 rounded">
            {account?.voice_version_label || 'v1'}
          </span>
          {account?.voice_version_seq && (
            <span className="text-xs px-2 py-1 bg-gray-800 text-gray-400 rounded">
              seq #{account.voice_version_seq}
            </span>
          )}
          {account?.voice_version_hash && (
            <span
              className="text-xs px-2 py-1 bg-gray-800 text-gray-400 rounded font-mono cursor-help"
              title={account.voice_version_hash}
            >
              {account.voice_version_hash.slice(0, 12)}…
            </span>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="App-loading">Loading voice…</p>
      ) : systemPrompt || personality || negSemantics.length > 0 ? (
        <div className="space-y-6">
          {systemPrompt && (
            <div>
              <h4 className="text-sm font-semibold text-orange-400 mb-2">System prompt</h4>
              <p className="text-sm text-gray-300 whitespace-pre-wrap bg-gray-950 p-3 rounded border border-gray-800">
                {systemPrompt}
              </p>
            </div>
          )}

          {personality && (
            <div>
              <h4 className="text-sm font-semibold text-orange-400 mb-2">Personality</h4>
              <p className="text-sm text-gray-300 whitespace-pre-wrap bg-gray-950 p-3 rounded border border-gray-800">
                {personality}
              </p>
            </div>
          )}

          {negSemantics.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-orange-400 mb-2">
                Negative semantics ({negSemantics.length})
              </h4>
              <ul className="text-sm text-gray-300 space-y-1 bg-gray-950 p-3 rounded border border-gray-800">
                {negSemantics.map((item: string) => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="text-gray-600 mt-0.5">—</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <p className="page-hint">No voice configuration set.</p>
      )}
    </section>
  );
}

function VoicePolishRulesSection() {
  return (
    <section className="hq-panel" aria-label="Voice polish rules">
      <h3 className="hq-panel__title">Voice polish rules (auto-applied)</h3>

      <div className="space-y-6">
        <div>
          <h4 className="text-sm font-semibold text-orange-400 mb-3">Auto-fixed phrases (~20)</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {VOICE_POLISH_RULES.bannedPhrases.map((rule) => (
              <div
                key={rule.pattern}
                className="bg-gray-950 p-2 rounded border border-gray-800 font-mono"
              >
                <span className="text-red-400">{rule.pattern}</span>
                {rule.replace && (
                  <>
                    <span className="text-gray-600"> → </span>
                    <span className="text-green-400">{rule.replace}</span>
                  </>
                )}
                {!rule.replace && <span className="text-gray-600"> → (removed)</span>}
              </div>
            ))}
          </div>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-orange-400 mb-2">Contrast patterns (soft-flag)</h4>
          <ul className="text-sm text-gray-300 space-y-1 bg-gray-950 p-3 rounded border border-gray-800">
            {VOICE_POLISH_RULES.contrastPatterns.map((pattern) => (
              <li key={pattern} className="flex items-start gap-2">
                <span className="text-yellow-600 mt-0.5">⚠</span>
                <span>{pattern}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-gray-500 mt-2 italic">
            Posts with these patterns are rejected and regenerated.
          </p>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-orange-400 mb-2">Punctuation rules</h4>
          <ul className="text-sm text-gray-300 space-y-1 bg-gray-950 p-3 rounded border border-gray-800">
            {VOICE_POLISH_RULES.punctuationRules.map((rule) => (
              <li key={rule} className="flex items-start gap-2">
                <span className="text-gray-600 mt-0.5">—</span>
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-orange-400 mb-2">Additional rules</h4>
          <ul className="text-sm text-gray-300 space-y-1 bg-gray-950 p-3 rounded border border-gray-800">
            {VOICE_POLISH_RULES.textRules.map((rule) => (
              <li key={rule} className="flex items-start gap-2">
                <span className="text-gray-600 mt-0.5">—</span>
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

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
    const storedVoice = revision && hasStoredVoiceText(revision) ? revision : null;
    const activeVoice = isCurrent && voice ? voice : null;
    const promptSource = storedVoice ?? activeVoice;

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

        {promptSource ? (
          <VoicePromptDetail voice={promptSource} />
        ) : isCurrent && voiceQuery.isLoading ? (
          <p className="App-loading">Loading voice…</p>
        ) : (
          <p className="page-hint">
            Prompt text was not recorded for this revision. Only revisions saved after the voice
            archive update include full prompt details.
          </p>
        )}
      </div>
    );
  };

  const currentRevision = revisions.find((r) => r.seq === currentSeq);

  return (
    <div className="page-content">
      <div className="page-header__actions page-content__toolbar">
        <Link to={`/accounts/${accountId}/settings`} className="voice-badge">
          Current: {currentVoice}
        </Link>
      </div>

      <CurrentVoiceSection
        account={accountQuery.data}
        voice={voiceQuery.data}
        revision={currentRevision}
        isLoading={voiceQuery.isLoading}
      />

      <VoicePolishRulesSection />

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
              const hasPrompt = revision && hasStoredVoiceText(revision);
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
                        <VoicePromptDetail voice={revision} />
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
