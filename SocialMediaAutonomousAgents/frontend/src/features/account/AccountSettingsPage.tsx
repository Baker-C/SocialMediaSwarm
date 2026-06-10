import { useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { AccountCard } from '../../components/AccountCard';
import { EmptyState } from '../../components/layout/EmptyState';
import { useAccount } from '../../hooks/queries/useAccounts';
import { useAppContext } from '../../app/AppContext';

export function AccountSettingsPage() {
  const { accountId } = useParams();
  const accountQuery = useAccount(accountId);
  const { openUpdateModal, setToast } = useAppContext();
  const queryClient = useQueryClient();

  if (accountQuery.isLoading) {
    return <p className="App-loading">Loading account…</p>;
  }

  if (!accountQuery.data) {
    return <EmptyState message="Account not found." />;
  }

  return (
    <section className="account-panel" aria-label={`Account ${accountId} settings`}>
      <AccountCard
        account={accountQuery.data}
        onUpdateClick={openUpdateModal}
        variant="detail"
      />
      <p className="page-hint">
        After saving changes, metrics refresh automatically. Use Connect with X in the update modal
        for OAuth.
      </p>
      <button
        type="button"
        className="btn btn--ghost"
        onClick={() => {
          void queryClient.invalidateQueries({ queryKey: ['accounts'] });
          setToast('Account data refreshed');
        }}
      >
        Refresh account data
      </button>
    </section>
  );
}
