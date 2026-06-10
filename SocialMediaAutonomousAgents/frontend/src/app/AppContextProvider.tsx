import { useEffect, useState, type ReactNode } from 'react';
import { AppContext, type AppContextValue } from './AppContext';
import { apiBaseUrl } from '../lib/api';

type AppContextProviderProps = {
  children: ReactNode;
};

export function AppContextProvider({ children }: AppContextProviderProps) {
  const [toast, setToast] = useState('');
  const [updateAccountId, setUpdateAccountId] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const t = window.setTimeout(() => setToast(''), 3800);
    return () => window.clearTimeout(t);
  }, [toast]);

  const value: AppContextValue = {
    apiBase: apiBaseUrl(),
    toast,
    setToast,
    updateAccountId,
    openUpdateModal: setUpdateAccountId,
    closeUpdateModal: () => setUpdateAccountId(null),
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
