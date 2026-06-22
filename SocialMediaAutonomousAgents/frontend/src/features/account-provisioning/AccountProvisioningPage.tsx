import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiBaseUrl } from '../../api/client';
import { mediaUrl } from '../../api/endpoints/personaChat';
import { usePersonaChat } from '../../hooks/usePersonaChat';
import type { PersonaSpec } from '../../types/domain/persona';
import { Button } from '../../components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { ErrorBanner } from '../../components/layout/ErrorBanner';
import { EmptyState } from '../../components/layout/EmptyState';

type Stage = 'chat' | 'review' | 'provisioning';

export function AccountProvisioningPage() {
  const apiBase = apiBaseUrl();
  const [accountId, setAccountId] = useState('');
  const [stage, setStage] = useState<Stage>('chat');

  const persona = usePersonaChat({ apiBase, accountId });

  // The account id isn't entered up front — populate it from the persona's handle once
  // proposed (operator can still override it while in the chat stage).
  useEffect(() => {
    if (persona.proposal?.handle && !accountId.trim()) {
      setAccountId(persona.proposal.handle);
    }
  }, [persona.proposal, accountId]);

  return (
    <div className="space-y-4">
      <div className="flex gap-1 text-xs tracking-wider text-neutral-500">
        <span className={stage === 'chat' ? 'text-orange-500' : ''}>CHAT</span>
        <span>→</span>
        <span className={stage === 'review' ? 'text-orange-500' : ''}>REVIEW</span>
        <span>→</span>
        <span className={stage === 'provisioning' ? 'text-orange-500' : ''}>PROVISION</span>
      </div>

      {stage === 'chat' && (
        <ChatStage
          persona={persona}
          onProceed={() => setStage('review')}
        />
      )}

      {stage === 'review' && persona.proposal && (
        <ReviewStage
          persona={persona}
          accountId={accountId}
          onAccountIdChange={setAccountId}
          onWritten={() => setStage('provisioning')}
        />
      )}

      {stage === 'provisioning' && (
        <ProvisioningStage accountId={accountId} />
      )}
    </div>
  );
}

type PersonaHook = ReturnType<typeof usePersonaChat>;

function ChatStage({
  persona,
  onProceed,
}: {
  persona: PersonaHook;
  onProceed: () => void;
}) {
  const [draft, setDraft] = useState('');
  const { messages, running, error, proposal, send } = persona;

  const handleSend = async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    await send(text);
  };

  return (
    <div className="space-y-4">
      {/* Top: chat transcript + composer */}
      <Card className="flex flex-col">
        <CardHeader>
          <CardTitle className="text-lg">Design the persona</CardTitle>
          <CardDescription>
            Describe the account you want. Claude proposes a structured persona.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col flex-1 gap-3">
          <div className="flex flex-col gap-2 min-h-[12rem] max-h-[28rem] overflow-auto">
            {messages.length === 0 && !error ? (
              <EmptyState message="Start by describing the niche, audience, and voice." />
            ) : null}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`max-w-[85%] rounded-md px-3 py-2 text-sm whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'self-end bg-primary text-primary-foreground'
                    : 'self-start bg-muted text-foreground'
                }`}
              >
                {msg.content}
              </div>
            ))}
          </div>

          {error ? <ErrorBanner message={error} /> : null}

          <div className="flex flex-col gap-2">
            <Textarea
              value={draft}
              placeholder="Describe the account…"
              disabled={running}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
            />
            <div className="flex justify-between items-center">
              <span className="text-xs text-neutral-500">Ctrl+Enter to send</span>
              <Button onClick={() => void handleSend()} disabled={running}>
                {running ? 'Thinking…' : 'Send'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Below: persona preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Persona preview</CardTitle>
          <CardDescription>Appears once Claude proposes a spec.</CardDescription>
        </CardHeader>
        <CardContent>
          {proposal ? (
            <div className="space-y-2 text-sm">
              <SpecRow label="Handle" value={`@${proposal.handle}`} />
              <SpecRow label="Display name" value={proposal.display_name} />
              <SpecRow label="Bio" value={proposal.bio} />
              <SpecRow label="Category" value={proposal.category} />
              <SpecRow label="Niches" value={proposal.niches.join(', ')} />
              <SpecRow label="Pipelines" value={(proposal.pipelines ?? []).join(', ')} />
              <SpecRow label="Personality" value={proposal.personality} />
              <Button className="mt-3 w-full" onClick={onProceed}>
                Review &amp; edit
              </Button>
            </div>
          ) : (
            <EmptyState message="No persona proposed yet." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SpecRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs tracking-wider text-neutral-400">{label.toUpperCase()}</div>
      <div className="text-foreground">{value || '—'}</div>
    </div>
  );
}

function ReviewStage({
  persona,
  accountId,
  onAccountIdChange,
  onWritten,
}: {
  persona: PersonaHook;
  accountId: string;
  onAccountIdChange: (id: string) => void;
  onWritten: () => void;
}) {
  const {
    proposal,
    images,
    imagesGenerating,
    running,
    error,
    validationErrors,
    written,
    slots,
    slotAccountId,
    setSlotAccountId,
    editSpec,
    approve,
    regenerate,
  } = persona;

  // Advance to provisioning once the account is written.
  useEffect(() => {
    if (written) onWritten();
  }, [written, onWritten]);

  // Auto-generate both images on first load when none exist yet.
  const didAutoGenerate = useRef(false);
  useEffect(() => {
    if (didAutoGenerate.current) return;
    if (!proposal) return;
    if (images?.avatar_asset_id || images?.header_asset_id) return;
    didAutoGenerate.current = true;
    void regenerate('avatar');
    void regenerate('header');
  }, [proposal, images, regenerate]);

  if (!proposal) return null;

  const field = (key: keyof PersonaSpec) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => editSpec({ [key]: e.target.value } as Partial<PersonaSpec>);

  return (
    <div className="space-y-4">
      {/* Images card first */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Images</CardTitle>
          <CardDescription>Avatar and header generated from the prompts.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Avatar: image → prompt → button */}
          <div className="space-y-2">
            {images?.avatar_asset_id ? (
              <img
                src={mediaUrl(images.avatar_asset_id)}
                alt="Avatar"
                className="w-24 h-24 rounded-full border border-neutral-700 object-cover"
              />
            ) : imagesGenerating.avatar ? (
              <p className="text-sm text-neutral-400">Generating profile picture…</p>
            ) : null}
            <LabeledTextarea
              label="Avatar prompt"
              value={proposal.avatar_prompt}
              onChange={field('avatar_prompt')}
            />
            <Button
              variant="outline"
              onClick={() => void regenerate('avatar')}
              disabled={imagesGenerating.avatar}
            >
              {imagesGenerating.avatar ? 'Generating…' : 'Regenerate profile picture'}
            </Button>
          </div>

          {/* Header: image → prompt → button */}
          <div className="space-y-2">
            {images?.header_asset_id ? (
              <img
                src={mediaUrl(images.header_asset_id)}
                alt="Header"
                className="w-full rounded-md border border-neutral-700"
              />
            ) : imagesGenerating.header ? (
              <p className="text-sm text-neutral-400">Generating banner…</p>
            ) : null}
            <LabeledTextarea
              label="Header prompt"
              value={proposal.header_prompt}
              onChange={field('header_prompt')}
            />
            <Button
              variant="outline"
              onClick={() => void regenerate('header')}
              disabled={imagesGenerating.header}
            >
              {imagesGenerating.header ? 'Generating…' : 'Regenerate banner'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Review persona card second */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Review persona</CardTitle>
          <CardDescription>Edit any field before provisioning.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <label className="block text-xs tracking-wider text-neutral-400 mb-1" htmlFor="review-account-id">
              ACCOUNT ID
            </label>
            <Input
              id="review-account-id"
              value={accountId}
              placeholder="Account ID"
              onChange={(e) => onAccountIdChange(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs tracking-wider text-neutral-400 mb-1" htmlFor="review-slot">
              PHONE ACCOUNT TO TAKE OVER
            </label>
            {slots.length === 0 ? (
              <p className="text-sm text-neutral-400">
                No un-souled phone accounts available — this persona will be parked as retired.
              </p>
            ) : (
              <select
                id="review-slot"
                value={slotAccountId}
                onChange={(e) => setSlotAccountId(e.target.value)}
                className="w-full rounded-md border border-neutral-700 bg-transparent px-3 py-2 text-sm"
              >
                {slots.map((s) => (
                  <option key={s.account_id} value={s.account_id}>
                    {s.account_id}
                    {s.phone_last4 ? ` — •••${s.phone_last4}` : ''}
                  </option>
                ))}
              </select>
            )}
          </div>
          <LabeledInput label="Handle" value={proposal.handle} onChange={field('handle')} />
          <LabeledInput
            label="Display name"
            value={proposal.display_name}
            onChange={field('display_name')}
          />
          <LabeledTextarea label="Bio" value={proposal.bio} onChange={field('bio')} />
          <LabeledInput label="Category" value={proposal.category} onChange={field('category')} />
          <LabeledInput
            label="Niches (comma-separated)"
            value={proposal.niches.join(', ')}
            onChange={(e) =>
              editSpec({
                niches: e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
          <LabeledInput
            label="Pipelines (comma-separated)"
            value={(proposal.pipelines ?? []).join(', ')}
            onChange={(e) =>
              editSpec({
                pipelines: e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
          <LabeledTextarea
            label="Personality"
            value={proposal.personality}
            onChange={field('personality')}
          />
          <LabeledTextarea
            label="Posting prompt"
            value={proposal.posting_prompt}
            onChange={field('posting_prompt')}
          />

          {validationErrors && validationErrors.length > 0 ? (
            <ErrorBanner
              title="Validation errors"
              message="Fix the issues below and try again."
              details={validationErrors}
            />
          ) : null}
          {error ? <ErrorBanner message={error} /> : null}

          <Button className="w-full" onClick={() => void approve()} disabled={running}>
            {running ? 'Initializing…' : 'Initialize account'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div>
      <label className="block text-xs tracking-wider text-neutral-400 mb-1">
        {label.toUpperCase()}
      </label>
      <Input value={value} onChange={onChange} />
    </div>
  );
}

function LabeledTextarea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
}) {
  return (
    <div>
      <label className="block text-xs tracking-wider text-neutral-400 mb-1">
        {label.toUpperCase()}
      </label>
      <Textarea value={value} onChange={onChange} className="min-h-[120px]" />
    </div>
  );
}

function ProvisioningStage({ accountId }: { accountId: string }) {
  // ponytail: no registration here — persona just fills a slot; X signup is a
  // separate desktop step. Add a "Sign up" surface on the account when needed.
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Account initialized</CardTitle>
        <CardDescription>
          {accountId} is ready. Sign it up on X from the desktop app when you want.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild>
          <Link to={`/accounts/${encodeURIComponent(accountId)}`}>Go to account</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
