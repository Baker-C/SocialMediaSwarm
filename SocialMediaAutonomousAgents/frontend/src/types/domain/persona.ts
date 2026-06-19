// Mirror of backend app/api/routes/persona_types.py + provisioning_types.py emit
// helpers (plan 03 §2, plan 05 §2). Read-only on the frontend; the SSE unions are 1:1
// with the backend `emit_*` builders (each frame has a `type` discriminant).

export interface PersonaSpec {
  handle: string;
  display_name: string;
  bio: string;
  category: string;
  personality: string;
  posting_prompt: string;
  avatar_prompt: string;
  header_prompt: string;
}

export type PersonaChatMessage = {
  role: 'user' | 'assistant';
  text: string;
};

export type PersonaChatRequest = {
  account_id: string;
  messages: PersonaChatMessage[];
  proposal?: PersonaSpec | null; // prior proposal echoed back (stateless server)
  approve?: boolean; // true => generate images + write the account
};

// plan 03 §2 — the chat / approve stream.
export type PersonaStreamEvent =
  | { type: 'assistant_message'; text: string }
  | { type: 'persona_preview'; spec: PersonaSpec }
  | { type: 'images_generating' }
  | { type: 'images_ready'; avatar_asset_id: string; header_asset_id: string }
  | { type: 'account_written'; account_id: string }
  | { type: 'validation_errors'; errors: string[] }
  | { type: 'error'; message: string }
  | { type: 'done' };

// plan 05 §2 — the live provisioning status stream.
export type ProvisioningStatusEvent =
  | {
      type: 'status';
      status: string;
      current_page: string;
      step_log: string[];
      error_message?: string;
    }
  | { type: 'done' }
  | { type: 'error'; message: string };

export type ProvisioningControlAction = 'continue' | 'cancel';
