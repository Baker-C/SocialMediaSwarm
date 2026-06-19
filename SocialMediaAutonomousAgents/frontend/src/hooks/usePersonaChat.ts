import { useCallback, useEffect, useRef, useState } from 'react';
import { streamPersonaChat, regenerateImages } from '../api/endpoints/personaChat';
import type {
  PersonaChatMessage,
  PersonaSpec,
  PersonaStreamEvent,
} from '../types/domain/persona';
import type { PersonaImages } from './personaChatReducer';

type UsePersonaChatOptions = {
  apiBase: string;
  accountId: string;
};

type UsePersonaChatResult = {
  messages: PersonaChatMessage[];
  running: boolean;
  error: string | null;
  proposal: PersonaSpec | null;
  images: PersonaImages | null;
  imagesGenerating: { avatar: boolean; header: boolean };
  written: string | null;
  validationErrors: string[] | null;
  send: (text: string) => Promise<void>;
  approve: () => Promise<void>;
  editSpec: (patch: Partial<PersonaSpec>) => void;
  regenerate: (target: 'avatar' | 'header') => Promise<void>;
};

// Copy of useBuilderChat, adapted to the persona event union (plan 08 §4). Keeps the
// abortRef + messagesRef/proposalRef refs and the unmount-abort effect.
export function usePersonaChat({
  apiBase,
  accountId,
}: UsePersonaChatOptions): UsePersonaChatResult {
  const [messages, setMessages] = useState<PersonaChatMessage[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<PersonaSpec | null>(null);
  const [images, setImages] = useState<PersonaImages | null>(null);
  const [imagesGenerating, setImagesGenerating] = useState<{ avatar: boolean; header: boolean }>({
    avatar: false,
    header: false,
  });
  const [written, setWritten] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[] | null>(null);

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
    async (newMessages: PersonaChatMessage[], approve: boolean) => {
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
        await streamPersonaChat(
          apiBase,
          {
            account_id: accountId,
            messages: newMessages,
            proposal: proposalRef.current,
            approve,
          },
          (event: PersonaStreamEvent) => {
            switch (event.type) {
              case 'assistant_message':
                setMessages((prev) => [...prev, { role: 'assistant', content: event.text }]);
                return;
              case 'persona_preview':
                setProposal(event.spec);
                setValidationErrors(null);
                return;
              case 'images_generating':
                setImagesGenerating({ avatar: true, header: true });
                return;
              case 'images_ready':
                setImagesGenerating({ avatar: false, header: false });
                setImages({
                  avatar_asset_id: event.avatar_asset_id,
                  header_asset_id: event.header_asset_id,
                });
                return;
              case 'account_written':
                setWritten(event.account_id);
                finalize(null);
                return;
              case 'validation_errors':
                setValidationErrors(event.errors);
                return;
              case 'error':
                finalize(event.message);
                return;
              case 'done':
                finalize(null);
                return;
              default:
                return;
            }
          },
          controller.signal
        );
      } catch (err) {
        if (!controller.signal.aborted) {
          const message = err instanceof Error ? err.message : 'Persona chat failed';
          finalize(message);
        }
      }
    },
    [apiBase, accountId]
  );

  const send = useCallback(
    async (text: string) => {
      if (running || !text.trim()) return;
      const newMessages: PersonaChatMessage[] = [
        ...messagesRef.current,
        { role: 'user', content: text.trim() },
      ];
      setMessages(newMessages);
      await stream(newMessages, false);
    },
    [running, stream]
  );

  const approve = useCallback(async () => {
    if (running) return;
    await stream(messagesRef.current, true);
  }, [running, stream]);

  const editSpec = useCallback((patch: Partial<PersonaSpec>) => {
    setProposal((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  const regenerate = useCallback(async (target: 'avatar' | 'header') => {
    const spec = proposalRef.current;
    if (running || !spec) return;
    setError(null);
    setImagesGenerating((prev) => ({ ...prev, [target]: true }));
    try {
      const body =
        target === 'avatar'
          ? { avatar_prompt: spec.avatar_prompt }
          : { header_prompt: spec.header_prompt };
      const result = await regenerateImages(body);
      setImages((prev) => {
        const base: PersonaImages = prev ?? { avatar_asset_id: '', header_asset_id: '' };
        return {
          avatar_asset_id: result.avatar_asset_id ?? base.avatar_asset_id,
          header_asset_id: result.header_asset_id ?? base.header_asset_id,
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Image regeneration failed');
    } finally {
      setImagesGenerating((prev) => ({ ...prev, [target]: false }));
    }
  }, [running]);

  return {
    messages,
    running,
    error,
    proposal,
    images,
    imagesGenerating,
    written,
    validationErrors,
    send,
    approve,
    editSpec,
    regenerate,
  };
}
