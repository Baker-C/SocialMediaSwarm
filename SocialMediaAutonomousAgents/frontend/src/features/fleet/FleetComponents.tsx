import { Link } from 'react-router-dom';
import type { LeaderboardRow, OpsAlert } from '../../analytics/selectors/fleetKpis';
import { DataTable, type DataTableColumn } from '../../components/data/DataTable';
import { formatAge, formatPercent } from '../../lib/format';

const leaderboardColumns: DataTableColumn<LeaderboardRow>[] = [
  {
    id: 'account',
    header: 'Account',
    accessor: (r) => (
      <Link to={`/accounts/${r.accountId}`} className="table-link">
        {r.accountId}
      </Link>
    ),
    sortValue: (r) => r.accountId,
  },
  { id: 'niche', header: 'Niche', accessor: (r) => r.niche, sortValue: (r) => r.niche },
  {
    id: 'avgEr',
    header: 'Avg ER',
    accessor: (r) => formatPercent(r.avgEr, 2),
    sortValue: (r) => r.avgEr ?? -1,
    align: 'right',
  },
  {
    id: 'growth',
    header: 'Follower growth',
    accessor: (r) => (r.followerGrowth != null ? r.followerGrowth : '—'),
    sortValue: (r) => r.followerGrowth ?? -Infinity,
    align: 'right',
  },
  {
    id: 'lastPost',
    header: 'Last post',
    accessor: (r) => formatAge(r.lastPostAge),
    sortValue: (r) => r.lastPostAge ?? '',
  },
  {
    id: 'oauth',
    header: 'OAuth',
    accessor: (r) => (r.hasOAuth ? '✓' : '—'),
    sortValue: (r) => (r.hasOAuth ? 1 : 0),
  },
];

type AccountLeaderboardProps = {
  rows: LeaderboardRow[];
};

export function AccountLeaderboard({ rows }: AccountLeaderboardProps) {
  return (
    <section className="fleet-section" aria-label="Account leaderboard">
      <h3 className="fleet-section__title">Leaderboard</h3>
      <DataTable
        columns={leaderboardColumns}
        rows={rows}
        rowKey={(r) => r.accountId}
        emptyMessage="No accounts to rank."
        ariaLabel="Account leaderboard by engagement"
      />
    </section>
  );
}

type OpsAlertStripProps = {
  alerts: OpsAlert[];
};

export function OpsAlertStrip({ alerts }: OpsAlertStripProps) {
  if (alerts.length === 0) {
    return null;
  }

  return (
    <section className="ops-alerts" aria-label="Operations alerts">
      <h3 className="ops-alerts__title">Ops alerts</h3>
      <ul className="ops-alerts__list">
        {alerts.slice(0, 12).map((a) => (
          <li key={`${a.kind}-${a.accountId}`} className={`ops-alerts__item ops-alerts__item--${a.kind}`}>
            <Link to={`/accounts/${a.accountId}`} className="ops-alerts__link">
              {a.accountId}
            </Link>
            <span>{a.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
