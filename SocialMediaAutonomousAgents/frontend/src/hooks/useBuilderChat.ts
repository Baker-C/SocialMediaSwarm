import { useCallback, useEffect, useRef, useState } from 'react';
import { streamBuilderChat } from '../api/endpoints/builderChat';
import type { BuilderChatMessage, BuilderStreamEvent } from '../types/domain/builder';
import type { PipelineSpec } from '../types/domain/pipelineSpec';

type BuilderProposal = {
  spec: PipelineSpec;
  mermaid: string;
  catalog_hash: string;
  soul_edit?: Record<string, unknown> | null;
};

type BuilderWritten = {
  spec_doc_id: string;
  status: 'champion' | 'challenger';
  version_label: string;
  soul_bumped: boolean;
};

type UseBuilderChatOptions = {
  apiBase: string;
  accountId: string;
  mode: 'create' | 'edit';
};

type UseBuilderChatResult = {
  messages: BuilderChatMessage[];
  running: boolean;
  error: string | null;
  proposal: BuilderProposal | null;
  written: BuilderWritten | null;
  send: (text: string) => Promise<void>;
  approve: () => Promise<void>;
};

export function useBuilderChat({
  apiBase,
  accountId,
  mode,
}: UseBuilderChatOptions): UseBuilderChatResult {
  const [messages, setMessages] = useState<BuilderChatMessage[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<BuilderProposal | null>(null);
  const [written, setWritten] = useState<BuilderWritten | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef(messages);
  const proposalRef = useRef(proposal);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    proposalRef.current = proposal;
  }, [proposal]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const stream = useCallback(
    async (newMessages: BuilderChatMessage[], approve: boolean) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setError(null);
      setRunning(true);

      let finalized = false;
      const finalize = (message: string | null) => {
        if (finalized) return;
        finalized = true;
        if (message) setError(message);
        setRunning(false);
      };

      try {
        await streamBuilderChat(
          apiBase,
          {
            account_id: accountId,
            mode,
            messages: newMessages,
            approve,
          },
          (event: BuilderStreamEvent) => {
            if (event.type === 'assistant_message') {
              setMessages((prev) => [
                ...prev,
                { role: 'assistant', text: event.text },
              ]);
              return;
            }

            if (event.type === 'validation_errors') {
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (!last || last.role !== 'assistant') return prev;
                return [
                  ...prev.slice(0, -1),
                  { ...last, validation_errors: event.errors },
                ];
              });
              return;
            }

            if (event.type === 'spec_preview') {
              const p: BuilderProposal = {
                spec: event.spec,
                mermaid: event.mermaid,
                catalog_hash: event.catalog_hash,
                soul_edit: event.soul_edit ?? null,
              };
              setProposal(p);
              setMessages((prev) => {
                const last = prev[prev.length - 1];
                if (!last || last.role !== 'assistant') return prev;
                return [
                  ...prev.slice(0, -1),
                  { ...last, proposed_spec: event.spec },
                ];
              });
              return;
            }

            if (event.type === 'spec_written') {
              const w: BuilderWritten = {
                spec_doc_id: event.spec_doc_id,
                status: event.status,
                version_label: event.version_label,
                soul_bumped: event.soul_bumped,
              };
              setWritten(w);
              finalize(null);
              return;
            }

            if (event.type === 'error') {
              finalize(event.message);
              return;
            }

            if (event.type === 'done') {
              finalize(null);
              return;
            }
          },
          controller.signal
        );
      } catch (err) {
        if (!controller.signal.aborted) {
          const message = err instanceof Error ? err.message : 'Builder chat failed';
          finalize(message);
        }
      }
    },
    [apiBase, accountId, mode]
  );

  const send = useCallback(
    async (text: string) => {
      if (running || !text.trim()) return;
      const newMessages: BuilderChatMessage[] = [...messagesRef.current, { role: 'user', text: text.trim() }];
      setMessages(newMessages);
      await stream(newMessages, false);
    },
    [running, stream]
  );

  const approve = useCallback(async () => {
    if (running) return;
    // Re-stream with approve:true; use current messages (which include proposed_spec from prior turn)
    await stream(messagesRef.current, true);
  }, [running, stream]);

  return {
    messages,
    running,
    error,
    proposal,
    written,
    send,
    approve,
  };
}
