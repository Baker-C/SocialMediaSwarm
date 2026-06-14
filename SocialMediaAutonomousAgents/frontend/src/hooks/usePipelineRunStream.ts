import { useCallback, useEffect, useRef, useState } from 'react';
import { streamForcePost } from '../api/endpoints/forcePost';
import { extractPipelineFailure, formatPipelineError } from '../lib/forcePostSteps';
import type { PipelineProgressPayload, PipelineRunStreamEvent } from '../types/pipelineProgress';

type UsePipelineRunStreamOptions = {
  apiBase: string;
  accountId: string;
  enabled?: boolean;
  onProgress?: (event: PipelineProgressPayload) => void;
  onComplete?: (result: unknown, failure: string | null) => void;
};

type UsePipelineRunStreamResult = {
  running: boolean;
  error: string | null;
  run: () => Promise<void>;
  abort: () => void;
};

export function usePipelineRunStream({
  apiBase,
  accountId,
  onProgress,
  onComplete,
}: UsePipelineRunStreamOptions): UsePipelineRunStreamResult {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const onProgressRef = useRef(onProgress);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onProgressRef.current = onProgress;
  }, [onProgress]);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const run = useCallback(async () => {
    const aid = accountId.trim();
    if (!aid || running) {
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setRunning(true);

    let finalized = false;
    const finalize = (message: string | null) => {
      if (finalized) {
        return;
      }
      finalized = true;
      if (message) {
        setError(message);
      }
    };

    try {
      await streamForcePost(
        apiBase,
        aid,
        (event: PipelineRunStreamEvent) => {
          if (event.type === 'progress') {
            onProgressRef.current?.(event);
            return;
          }
          if (event.type === 'error') {
            const message = formatPipelineError(event.message);
            finalize(message);
            onCompleteRef.current?.(null, message);
            return;
          }
          const failure =
            (typeof event.failure === 'string' && event.failure.trim()) ||
            extractPipelineFailure(event.result);
          if (failure) {
            finalize(formatPipelineError(failure));
            onCompleteRef.current?.(event.result, failure);
          } else {
            onCompleteRef.current?.(event.result, null);
          }
        },
        controller.signal
      );
    } catch (err) {
      if (!controller.signal.aborted) {
        const message = err instanceof Error ? err.message : 'Pipeline run failed';
        const formatted = formatPipelineError(message);
        finalize(formatted);
        onCompleteRef.current?.(null, formatted);
      }
    } finally {
      if (abortRef.current === controller) {
        if (!finalized) {
          const message = 'Pipeline run ended unexpectedly.';
          finalize(message);
          onCompleteRef.current?.(null, message);
        }
        setRunning(false);
        abortRef.current = null;
      }
    }
  }, [accountId, apiBase, running]);

  return { running, error, run, abort };
}
