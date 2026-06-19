import {
  initialPersonaChatState,
  personaChatReduce,
} from './personaChatReducer';
import type { PersonaSpec } from '../types/domain/persona';

const spec: PersonaSpec = {
  handle: 'oracle',
  display_name: 'The Oracle',
  bio: 'Sees all.',
  category: 'mystic',
  personality: 'cryptic',
  posting_prompt: 'speak in riddles',
  avatar_prompt: 'glowing eyes',
  header_prompt: 'cosmic banner',
};

describe('personaChatReduce', () => {
  it('appends assistant messages', () => {
    const next = personaChatReduce(initialPersonaChatState(), {
      type: 'assistant_message',
      text: 'Tell me more.',
    });
    expect(next.messages).toEqual([{ role: 'assistant', text: 'Tell me more.' }]);
  });

  it('sets the proposal on persona_preview and clears prior validation errors', () => {
    const start = { ...initialPersonaChatState(), validationErrors: ['old'] };
    const next = personaChatReduce(start, { type: 'persona_preview', spec });
    expect(next.proposal).toEqual(spec);
    expect(next.validationErrors).toBeNull();
  });

  it('tracks image generation lifecycle', () => {
    const gen = personaChatReduce(initialPersonaChatState(), { type: 'images_generating' });
    expect(gen.imagesGenerating).toBe(true);
    const ready = personaChatReduce(gen, {
      type: 'images_ready',
      avatar_asset_id: 'a1',
      header_asset_id: 'h1',
    });
    expect(ready.imagesGenerating).toBe(false);
    expect(ready.images).toEqual({ avatar_asset_id: 'a1', header_asset_id: 'h1' });
  });

  it('records the written account id', () => {
    const next = personaChatReduce(initialPersonaChatState(), {
      type: 'account_written',
      account_id: 'midnight_oracle',
    });
    expect(next.written).toBe('midnight_oracle');
  });

  it('captures validation errors', () => {
    const next = personaChatReduce(initialPersonaChatState(), {
      type: 'validation_errors',
      errors: ['handle taken'],
    });
    expect(next.validationErrors).toEqual(['handle taken']);
  });

  it('is a no-op for done / error', () => {
    const start = initialPersonaChatState([{ role: 'user', text: 'hi' }]);
    expect(personaChatReduce(start, { type: 'done' })).toEqual(start);
    expect(personaChatReduce(start, { type: 'error', message: 'boom' })).toEqual(start);
  });
});
