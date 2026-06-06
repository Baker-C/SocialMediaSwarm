import type { AccountSummary } from '../types';
import { formatAge, formatGrowth, formatShortDate } from '../lib/format';

type AccountCardProps = {
  account: AccountSummary;
  onUpdateClick: (accountId: string) => void;
  /** Full-width detail layout on account tab */
  variant?: 'card' | 'detail';
};

export function AccountCard({ account, onUpdateClick, variant = 'card' }: AccountCardProps) {
  const handle = account.twitter_handle?.trim();
  const growth = formatGrowth(account.follower_growth_vs_registered);
  const recent = account.recent_post;
  const viewsLabel =
    recent?.views !== null && recent?.views !== undefined ? String(recent.views) : '—';

  return (
    <article
      className={`account-card${variant === 'detail' ? ' account-card--detail' : ''}`}
      aria-labelledby={`acct-${account.account_id}-title`}
    >
      <header className="account-card__head">
        <div>
          <h2 className="account-card__title" id={`acct-${account.account_id}-title`}>
            {account.account_id}
          </h2>
          <p className="account-card__niche">{account.niche}</p>
        </div>
        <span className={`account-card__status account-card__status--${account.status}`}>
          {account.status}
        </span>
      </header>

      <p
        className="account-card__growth"
        title="Change in follower count since registration baseline"
      >
        <span className="account-card__growth-label">Growth</span>
        <span className="account-card__growth-value">{growth}</span>
      </p>

      <section className="account-card__recap" aria-label="Most recent post">
        <h3 className="account-card__recap-title">Latest post</h3>
        {recent?.snippet ? (
          <>
            <p className="account-card__recap-text">{recent.snippet}</p>
            <p className="account-card__recap-meta">
              {formatShortDate(recent.posted_at ?? undefined)}
              {recent.post_id ? (
                <span className="account-card__recap-id"> · id {recent.post_id}</span>
              ) : null}
            </p>
            <p className="account-card__recap-views">
              Views (last post): <strong>{viewsLabel}</strong>
            </p>
          </>
        ) : (
          <p className="account-card__recap-empty">No posts recorded yet for this account.</p>
        )}
      </section>

      <dl className="account-card__stats">
        <div className="account-card__stat">
          <dt>Followers</dt>
          <dd>{account.followers}</dd>
        </div>
        <div className="account-card__stat">
          <dt>Posts (total)</dt>
          <dd>{account.posts_total}</dd>
        </div>
        <div className="account-card__stat">
          <dt>Time on platform</dt>
          <dd>{formatAge(account.registered_at)}</dd>
        </div>
        <div className="account-card__stat">
          <dt>Registered</dt>
          <dd>{formatShortDate(account.registered_at ?? undefined)}</dd>
        </div>
        <div className="account-card__stat account-card__stat--wide">
          <dt>Last interval slot</dt>
          <dd>{account.last_interval_slot ?? '—'}</dd>
        </div>
        {handle ? (
          <div className="account-card__stat account-card__stat--wide">
            <dt>Handle</dt>
            <dd>{handle}</dd>
          </div>
        ) : null}
        {account.has_credentials === false ? (
          <div className="account-card__stat account-card__stat--wide">
            <dt>X connection</dt>
            <dd className="account-card__warn">Not connected — use Update account → Connect with X</dd>
          </div>
        ) : null}
      </dl>

      <div className="account-card__actions">
        <button
          type="button"
          className="account-card__btn"
          onClick={() => onUpdateClick(account.account_id)}
        >
          Update account
        </button>
      </div>
    </article>
  );
}
