// Mirror of backend app/api/routes/agent_builder_types.py (doc 10 §6). Read-only on the frontend.
import type { PipelineSpec } from './pipelineSpec';
import type { ValidationError } from './validation';

export type BuilderChatMessage = {
  role: 'user' | 'assistant';
  text: string;
  // When an assistant turn proposed a spec, the client echoes the streamed
  // spec_preview.spec + validation_errors back here so the next turn / approve can
  // reference the exact prior proposal without a server session (doc 10 §6.1).
  proposed_spec?: PipelineSpec | null;
  validation_errors?: ValidationError[] | null;
};

export type BuilderChatRequest = {
  account_id: string;
  mode: 'create' | 'edit';            // doc 10: "create" provisions; "edit" stages a challenger
  messages: BuilderChatMessage[];
  approve?: boolean;                  // true => write the last proposed_spec (re-validated first)
};

// doc 10 §6.3 — every frame has a `type` discriminant. NOTE: the assistant text is
// delivered WHOLE in one `assistant_message` per turn (doc 10 does NOT token-stream;
// it emits the parsed BuilderDraft.reply after the single Claude call). The right
// pane renders on `spec_preview`; errors surface on `validation_errors`.
export type BuilderStreamEvent =
  | { type: 'assistant_message'; text: string }
  | { type: 'validation_errors'; errors: ValidationError[] }
  | { type: 'spec_preview'; mermaid: string; spec: PipelineSpec;
      catalog_hash: string; soul_edit?: Record<string, unknown> | null }
  | { type: 'spec_written'; spec_doc_id: string; status: 'champion' | 'challenger';
      version_label: string; soul_bumped: boolean; account_id: string }
  | { type: 'error'; message: string }
  | { type: 'done' };
