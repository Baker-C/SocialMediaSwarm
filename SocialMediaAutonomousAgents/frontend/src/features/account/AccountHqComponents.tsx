import { Link } from 'react-router-dom';
import type { AccountSummary } from '../../types';
import { formatGrowth, formatShortDate } from '../../lib/format';

type AccountHeaderProps = {
  account: AccountSummary;
};

export function AccountHeader({ account }: AccountHeaderProps) {
  const voiceLabel = account.voice_version_label ?? 'default';
  const voiceSeq = account.voice_version_seq;

  return (
    <header className="account-header">
      <div>
        <h2 className="account-header__title">{account.account_id}</h2>
        <p className="account-header__meta">
          {account.niche} · @{account.twitter_handle?.replace(/^@/, '') || '—'} ·{' '}
          {account.followers.toLocaleString()} followers · {formatGrowth(account.follower_growth_vs_registered)}
        </p>
      </div>
      <span className="voice-badge" title="Current voice version">
        Voice {voiceLabel}
        {voiceSeq != null ? ` (#${voiceSeq})` : ''}
      </span>
    </header>
  );
}

type AccountKpiStripProps = {
  trackedPosts: number | null;
  avgEr: number | null;
  avgReply: number | null;
  avgLike: number | null;
  followerDeltaGap: number | null;
};

export function AccountKpiStrip({
  trackedPosts,
  avgEr,
  avgReply,
  avgLike,
  followerDeltaGap,
}: AccountKpiStripProps) {
  const tiles = [
    { label: 'Tracked posts', value: trackedPosts?.toLocaleString() ?? '—' },
    { label: 'Avg ER', value: avgEr != null ? `${(avgEr * 100).toFixed(2)}%` : '—' },
    { label: 'Avg reply rate', value: avgReply != null ? `${(avgReply * 100).toFixed(2)}%` : '—' },
    { label: 'Avg like rate', value: avgLike != null ? `${(avgLike * 100).toFixed(2)}%` : '—' },
    {
      label: 'Follower Δ gap',
      value: followerDeltaGap != null ? followerDeltaGap.toFixed(3) : '—',
      title: 'Engagement gap between positive vs non-positive follower delta buckets',
    },
  ];

  return (
    <div className="kpi-strip" aria-label="Account KPIs">
      {tiles.map((t) => (
        <div key={t.label} className="kpi-strip__tile" title={t.title}>
          <span className="kpi-strip__label">{t.label}</span>
          <span className="kpi-strip__value">{t.value}</span>
        </div>
      ))}
    </div>
  );
}

type CadenceGaugeProps = {
  lastPostAt: string | null | undefined;
  intervalMinutes?: number;
};

export function CadenceGauge({ lastPostAt, intervalMinutes = 30 }: CadenceGaugeProps) {
  const ageMs = lastPostAt ? Date.now() - Date.parse(lastPostAt) : null;
  const ageHours = ageMs != null && !Number.isNaN(ageMs) ? ageMs / 3600000 : null;
  const overdue = ageHours != null && ageHours > intervalMinutes / 60;

  return (
    <div className={`cadence-gauge${overdue ? ' cadence-gauge--overdue' : ''}`}>
      <span className="cadence-gauge__label">Posting cadence</span>
      <span className="cadence-gauge__value">
        Last post {lastPostAt ? formatShortDate(lastPostAt) : 'never'} · target every{' '}
        {intervalMinutes}m
      </span>
      {overdue ? (
        <span className="cadence-gauge__warn">Past expected interval</span>
      ) : null}
    </div>
  );
}

type QuickLinksProps = {
  accountId: string;
};

export function AccountQuickLinks({ accountId }: QuickLinksProps) {
  const links = [
    { to: `/accounts/${accountId}/posts`, label: 'Posts' },
    { to: `/accounts/${accountId}/references`, label: 'References' },
    { to: `/accounts/${accountId}/pipeline`, label: 'Pipeline' },
    { to: `/accounts/${accountId}/voice`, label: 'Voice' },
  ];
  return (
    <nav className="quick-links" aria-label="Quick links">
      {links.map((l) => (
        <Link key={l.to} to={l.to} className="quick-links__item">
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
