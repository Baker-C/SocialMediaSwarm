import { RouterProvider } from 'react-router-dom';
import './App.css';
import { UpdateAccountModal } from './components/UpdateAccountModal';
import { AppContextProvider } from './app/AppContextProvider';
import { AppProviders } from './app/AppProviders';
import { useAppContext } from './app/AppContext';
import { router } from './app/routes';
import { useQueryClient } from '@tanstack/react-query';

function AppShell() {
  const { toast, updateAccountId, closeUpdateModal, setToast, apiBase } = useAppContext();
  const queryClient = useQueryClient();

  return (
    <>
      {toast ? (
        <div className="toast" role="status">
          {toast}
        </div>
      ) : null}

      {updateAccountId ? (
        <UpdateAccountModal
          apiBase={apiBase}
          accountId={updateAccountId}
          onClose={closeUpdateModal}
          onSaved={() => {
            closeUpdateModal();
            setToast('Updated Account Successfully');
            void queryClient.invalidateQueries();
          }}
        />
      ) : null}

      <RouterProvider router={router} />
    </>
  );
}

function App() {
  return (
    <AppProviders>
      <AppContextProvider>
        <AppShell />
      </AppContextProvider>
    </AppProviders>
  );
}

export default App;
