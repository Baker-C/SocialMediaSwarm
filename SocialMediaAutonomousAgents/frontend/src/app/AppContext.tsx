import { createContext, useContext } from 'react';

export type AppContextValue = {
  apiBase: string;
  toast: string;
  setToast: (message: string) => void;
  updateAccountId: string | null;
  openUpdateModal: (accountId: string) => void;
  closeUpdateModal: () => void;
};

export const AppContext = createContext<AppContextValue | null>(null);

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error('useAppContext must be used within AppContext provider');
  }
  return ctx;
}
