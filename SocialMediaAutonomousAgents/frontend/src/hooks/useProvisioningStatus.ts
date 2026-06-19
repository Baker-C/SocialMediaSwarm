import { useCallback, useEffect, useRef, useState } from 'react';
import {
  sendControl,
  startProvisioning,
  streamProvisioningStatus,
} from '../api/endpoints/provisioning';
import type { ProvisioningStatusEvent } from '../types/domain/persona';

type UseProvisioningStatusOptions = {
  apiBase: string;
  accountId: string;
};

type UseProvisioningStatusResult = {
  status: string;
  currentPage: string;
  stepLog: string[];
  error: string | null;
  running: boolean;
  awaitingCaptcha: boolean;
  continue: () => Promise<void>;
  cancel: () => Promise<void>;
};

// Drives the live-status stage (plan 08 §4). Starts provisioning + tails the SSE status
// stream on mount; exposes the CAPTCHA continue / cancel controls.
export function useProvisioningStatus({
  apiBase,
  accountId,
}: UseProvisioningStatusOptions): UseProvisioningStatusResult {
  const [status, setStatus] = useState<string>('starting');
  const [currentPage, setCurrentPage] = useState<string>('');
  const [stepLog, setStepLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(true);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;

    const run = async () => {
      try {
        await startProvisioning(accountId);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to start provisioning');
          setRunning(false);
        }
        return;
      }

      try {
        await streamProvisioningStatus(
          apiBase,
          accountId,
          (event: ProvisioningStatusEvent) => {
            if (event.type === 'status') {
              setStatus(event.status);
              setCurrentPage(event.current_page);
              setStepLog(event.step_log);
              if (event.error_message) setError(event.error_message);
              return;
            }
            if (event.type === 'error') {
              setError(event.message);
              setRunning(false);
              return;
            }
            if (event.type === 'done') {
              setRunning(false);
              return;
            }
          },
          controller.signal
        );
      } catch (err) {
        if (!cancelled && !controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Provisioning status stream failed');
          setRunning(false);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
      controller.abort();
    };
    // start once per account
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, accountId]);

  const awaitingCaptcha = status === 'awaiting_captcha';

  const continueProvisioning = useCallback(async () => {
    try {
      await sendControl(accountId, 'continue');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send continue');
    }
  }, [accountId]);

  const cancel = useCallback(async () => {
    try {
      await sendControl(accountId, 'cancel');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel');
    }
  }, [accountId]);

  return {
    status,
    currentPage,
    stepLog,
    error,
    running,
    awaitingCaptcha,
    continue: continueProvisioning,
    cancel,
  };
}
