import { AccountCard } from '../components/AccountCard';
import type { AccountSummary } from '../types';

type AccountPanelProps = {
  account: AccountSummary;
  onUpdateClick: (accountId: string) => void;
};

export function AccountPanel({ account, onUpdateClick }: AccountPanelProps) {
  return (
    <section className="account-panel" aria-label={`Account ${account.account_id}`}>
      <AccountCard account={account} onUpdateClick={onUpdateClick} variant="detail" />
    </section>
  );
}
