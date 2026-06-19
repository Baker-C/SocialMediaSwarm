import type {
  PersonaChatMessage,
  PersonaSpec,
  PersonaStreamEvent,
} from '../types/domain/persona';

export type PersonaImages = {
  avatar_asset_id: string;
  header_asset_id: string;
};

// Pure event -> state projection for the persona chat stream. Extracted so it can be
// unit-tested in isolation (cf. flowReducer.test.ts). `running` / `error` are owned by
// the hook's stream lifecycle, not here.
export type PersonaChatState = {
  messages: PersonaChatMessage[];
  proposal: PersonaSpec | null;
  images: PersonaImages | null;
  imagesGenerating: boolean;
  written: string | null; // account_id once written
  validationErrors: string[] | null;
};

export function initialPersonaChatState(
  messages: PersonaChatMessage[] = []
): PersonaChatState {
  return {
    messages,
    proposal: null,
    images: null,
    imagesGenerating: false,
    written: null,
    validationErrors: null,
  };
}

export function personaChatReduce(
  state: PersonaChatState,
  event: PersonaStreamEvent
): PersonaChatState {
  switch (event.type) {
    case 'assistant_message':
      return {
        ...state,
        messages: [...state.messages, { role: 'assistant', text: event.text }],
      };
    case 'persona_preview':
      return { ...state, proposal: event.spec, validationErrors: null };
    case 'images_generating':
      return { ...state, imagesGenerating: true };
    case 'images_ready':
      return {
        ...state,
        imagesGenerating: false,
        images: {
          avatar_asset_id: event.avatar_asset_id,
          header_asset_id: event.header_asset_id,
        },
      };
    case 'account_written':
      return { ...state, written: event.account_id };
    case 'validation_errors':
      return { ...state, validationErrors: event.errors };
    case 'error':
    case 'done':
    default:
      return state;
  }
}
