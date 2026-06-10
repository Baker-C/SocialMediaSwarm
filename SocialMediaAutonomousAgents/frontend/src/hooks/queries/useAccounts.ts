import { useQuery } from '@tanstack/react-query';
import { fetchAccounts } from '../../api/endpoints/accounts';
import type { AccountSummary } from '../../types';

export function useAccounts() {
  return useQuery<AccountSummary[], Error>({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
  });
}

export function useAccount(accountId: string | undefined) {
  const accountsQuery = useAccounts();

  const account =
    accountId != null
      ? accountsQuery.data?.find((a: AccountSummary) => a.account_id === accountId)
      : undefined;

  return {
    ...accountsQuery,
    data: account,
  };
}
