'use client';

/**
 * The person's own phone number — declared, then verified by a call (phone as
 * a channel, lots 1-2-5).
 *
 * LIA may call the account holder WITHOUT a confirmation card only on a number
 * they declared here and then heard LIA read a code on. So the section is the
 * whole identity contract, in three panels:
 *
 *  - the number, shown WHOLE and editable — a masked number cannot be checked
 *    for the typo that would send the owner's context to a stranger;
 *  - the verification: a button places the call, and the code field appears
 *    only while a spoken code is pending (a field that is always there invites
 *    a guess);
 *  - the call mode (ADR-301): Live — the voice hands every request to the
 *    chat, which acts in the conversation — or Live direct — the voice reads
 *    LIA's tools itself and the call is relayed at its end;
 *  - the switch that decides whether an owner call carries the chat's context
 *    beyond free/busy — shown under Live direct alone, since a Live call
 *    reads nothing itself — and the domains a voice may read, ALWAYS shown:
 *    they govern every direct voice surface, the browser's direct session
 *    included (ADR-300 wave 4), whatever mode the phone runs in.
 *
 * A refusal is the backend's own translated sentence, attached to the field it
 * concerns (`aria-invalid` + `role="alert"`), never a generic toast.
 */

import { useState, type FormEvent } from 'react';
import { CheckCircle2, PhoneCall, Smartphone } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Switch } from '@/components/ui/switch';
import { CallModeField } from '@/components/settings/CallModeField';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useTelephonyIdentity,
  type UseTelephonyIdentityReturn,
} from '@/hooks/useTelephonyIdentity';
import type { TelephonyIdentity } from '@/types/telephony';
import type { BaseSettingsProps } from '@/types/settings';
import type { Language } from '@/i18n/settings';

/** A section action: `null` on success, the backend's sentence on refusal. */
type Refusal = string | null;

const DEFAULT_CODE_LIFETIME_SECONDS = 600;

// ---------------------------------------------------------------------------
// 1. The number, whole
// ---------------------------------------------------------------------------

interface NumberPanelProps {
  lng: Language;
  identity: TelephonyIdentity;
  busy: boolean;
  onSave: (raw: string) => Promise<Refusal>;
  onClear: () => Promise<Refusal>;
}

function NumberPanel({ lng, identity, busy, onSave, onClear }: NumberPanelProps) {
  const { t } = useTranslation(lng);
  // `null` = untouched: the field then shows the server's normalised form
  // (« 06 12… » typed comes back as E.164), and a save that succeeds returns
  // to it — no effect needed to mirror a prop into state.
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<Refusal>(null);
  const value = draft ?? identity.phone_number ?? '';

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const refusal = await onSave(value.trim());
    setError(refusal);
    if (!refusal) setDraft(null);
  };

  const clear = async () => {
    const refusal = await onClear();
    setError(refusal);
    if (!refusal) setDraft(null);
  };

  return (
    <form onSubmit={save} className="space-y-2" noValidate>
      <Input
        id="telephony-identity-number"
        label={t('settings.telephony.identity.number_label')}
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        placeholder={t('settings.telephony.identity.number_placeholder')}
        value={value}
        onChange={event => {
          setDraft(event.target.value);
          setError(null);
        }}
        error={error ?? undefined}
        disabled={busy}
      />
      <p className="text-xs text-muted-foreground">
        {t('settings.telephony.identity.number_help')}
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="submit" size="sm" disabled={busy || !value.trim()}>
          {t('common.save')}
        </Button>
        {identity.phone_number && (
          <Button type="button" size="sm" variant="ghost" onClick={clear} disabled={busy}>
            {t('settings.telephony.identity.remove')}
          </Button>
        )}
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// 2. The verification: a call, then a code
// ---------------------------------------------------------------------------

interface VerificationPanelProps {
  lng: Language;
  identity: TelephonyIdentity;
  busy: boolean;
  codeExpiresInSeconds: number | null;
  onStart: () => Promise<Refusal>;
  onConfirm: (code: string) => Promise<Refusal>;
}

function VerifiedLine({ lng, verifiedAt }: { lng: Language; verifiedAt: string | null }) {
  const { t } = useTranslation(lng);
  const date = verifiedAt ? new Date(verifiedAt) : null;
  if (!date || Number.isNaN(date.getTime())) return null;
  return (
    <p className="text-xs text-muted-foreground">
      {t('settings.telephony.identity.verified_at', {
        date: date.toLocaleString(lng, { dateStyle: 'short', timeStyle: 'short' }),
      })}
    </p>
  );
}

function CodeForm({
  lng,
  busy,
  codeExpiresInSeconds,
  onStart,
  onConfirm,
}: Omit<VerificationPanelProps, 'identity'>) {
  const { t } = useTranslation(lng);
  const [code, setCode] = useState('');
  const [error, setError] = useState<Refusal>(null);
  const minutes = Math.max(
    1,
    Math.round((codeExpiresInSeconds ?? DEFAULT_CODE_LIFETIME_SECONDS) / 60)
  );

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    const refusal = await onConfirm(code.trim());
    setError(refusal);
    if (!refusal) setCode('');
  };

  return (
    <form onSubmit={confirm} className="space-y-2" noValidate>
      <p className="text-sm">{t('settings.telephony.identity.code_pending', { minutes })}</p>
      <Input
        id="telephony-identity-code"
        label={t('settings.telephony.identity.code_label')}
        inputMode="numeric"
        autoComplete="one-time-code"
        value={code}
        onChange={event => {
          setCode(event.target.value);
          setError(null);
        }}
        error={error ?? undefined}
        disabled={busy}
      />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="submit" size="sm" disabled={busy || !code.trim()}>
          {t('settings.telephony.identity.confirm_code')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => void onStart()}
          disabled={busy}
        >
          {t('settings.telephony.identity.call_again')}
        </Button>
      </div>
    </form>
  );
}

function VerificationBadge({ lng, verified }: { lng: Language; verified: boolean }) {
  const { t } = useTranslation(lng);
  if (verified) {
    return (
      <Badge
        variant="success"
        size="sm"
        icon={<CheckCircle2 className="h-3 w-3" aria-hidden="true" />}
      >
        {t('settings.telephony.identity.verified')}
      </Badge>
    );
  }
  return (
    <Badge variant="warning" size="sm">
      {t('settings.telephony.identity.unverified')}
    </Badge>
  );
}

function UnverifiedSteps(props: VerificationPanelProps) {
  const { lng, identity, busy, onStart } = props;
  const { t } = useTranslation(lng);
  const [startError, setStartError] = useState<Refusal>(null);

  const start = async (): Promise<Refusal> => {
    const refusal = await onStart();
    setStartError(refusal);
    return refusal;
  };

  return (
    <>
      <p className="text-xs text-muted-foreground">
        {t('settings.telephony.identity.verification_help')}
      </p>
      {!identity.verification_pending && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={start}
          disabled={busy || !identity.phone_number}
        >
          <PhoneCall className="mr-2 h-4 w-4" aria-hidden="true" />
          {t('settings.telephony.identity.verify_by_call')}
        </Button>
      )}
      {startError && (
        <p role="alert" className="text-sm text-destructive">
          {startError}
        </p>
      )}
      {identity.verification_pending && <CodeForm {...props} onStart={start} />}
    </>
  );
}

function VerificationPanel(props: VerificationPanelProps) {
  const { lng, identity } = props;
  const { t } = useTranslation(lng);
  return (
    <div className="rounded-lg border border-border/60 bg-card/50 p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">
          {t('settings.telephony.identity.verification_title')}
        </span>
        <VerificationBadge lng={lng} verified={identity.verified} />
      </div>
      {identity.verified ? (
        <VerifiedLine lng={lng} verifiedAt={identity.verified_at} />
      ) : (
        <UnverifiedSteps {...props} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. The context switch
// ---------------------------------------------------------------------------

function RichContextSwitch({
  lng,
  identity,
  busy,
  onChange,
}: {
  lng: Language;
  identity: TelephonyIdentity;
  busy: boolean;
  onChange: (enabled: boolean) => Promise<Refusal>;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3">
      <div className="flex-1">
        <p className="text-sm font-medium">{t('settings.telephony.identity.rich_context_label')}</p>
        <p className="text-xs text-muted-foreground">
          {t('settings.telephony.identity.rich_context_help')}
        </p>
      </div>
      <Switch
        checked={identity.rich_context_enabled}
        onCheckedChange={value => void onChange(value)}
        disabled={busy}
        aria-label={t('settings.telephony.identity.rich_context_label')}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// The domains the phone may read for this person (lot 8)
// ---------------------------------------------------------------------------

/** The memories domain reads as `context` in the register; the person knows it as memory. */
const MEMORY_DOMAIN = 'context';

function domainLabelKey(domain: string): string {
  return domain === MEMORY_DOMAIN
    ? 'settings.telephony.identity.domain_memory'
    : `treatments.domains.${domain}`;
}

function DomainsPanel({
  lng,
  identity,
  busy,
  onChange,
}: {
  lng: Language;
  identity: TelephonyIdentity;
  busy: boolean;
  onChange: (domains: string[]) => Promise<Refusal>;
}) {
  const { t } = useTranslation(lng);
  const disabled = new Set(identity.disabled_domains);
  const toggle = (domain: string, on: boolean) => {
    const next = new Set(disabled);
    if (on) next.delete(domain);
    else next.add(domain);
    void onChange(identity.available_domains.filter(d => next.has(d)));
  };
  const rows = identity.available_domains.map(domain => ({
    domain,
    label: t(domainLabelKey(domain)),
  }));
  rows.sort((a, b) => a.label.localeCompare(b.label, lng));

  return (
    <fieldset className="space-y-2 rounded-lg border bg-card p-3">
      <legend className="px-1 text-sm font-medium">
        {t('settings.telephony.identity.domains_title')}
      </legend>
      <p className="text-xs text-muted-foreground">
        {t('settings.telephony.identity.domains_help')}
      </p>
      <ul className="grid gap-2 sm:grid-cols-2">
        {rows.map(({ domain, label }) => (
          <li key={domain} className="flex items-center justify-between gap-3">
            <span className="text-sm">{label}</span>
            <Switch
              checked={!disabled.has(domain)}
              onCheckedChange={value => toggle(domain, value)}
              disabled={busy}
              aria-label={label}
            />
          </li>
        ))}
      </ul>
    </fieldset>
  );
}

// ---------------------------------------------------------------------------
// The section
// ---------------------------------------------------------------------------

function IdentityPanels({ lng, hook }: { lng: Language; hook: UseTelephonyIdentityReturn }) {
  const { identity, isLoading, isBusy } = hook;
  if (isLoading || !identity) return <LoadingSpinner size="sm" />;
  return (
    <div className="space-y-4">
      <NumberPanel
        lng={lng}
        identity={identity}
        busy={isBusy}
        onSave={hook.setNumber}
        onClear={hook.clearNumber}
      />
      <VerificationPanel
        lng={lng}
        identity={identity}
        busy={isBusy}
        codeExpiresInSeconds={hook.codeExpiresInSeconds}
        onStart={hook.startVerification}
        onConfirm={hook.confirmCode}
      />
      <CallModeField
        lng={lng}
        id="telephony-identity-call-mode"
        identity={identity}
        busy={isBusy}
        onChange={hook.setCallMode}
      />
      {identity.call_mode_effective === 'direct' && (
        <RichContextSwitch
          lng={lng}
          identity={identity}
          busy={isBusy}
          onChange={hook.setRichContext}
        />
      )}
      <DomainsPanel
        lng={lng}
        identity={identity}
        busy={isBusy}
        onChange={hook.setDisabledDomains}
      />
    </div>
  );
}

export default function TelephonyIdentitySection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const hook = useTelephonyIdentity();

  if (hook.isUnavailable) return null;

  return (
    <SettingsSection
      value="telephony-identity"
      title={t('settings.telephony.identity.title')}
      description={t('settings.telephony.identity.description')}
      icon={Smartphone}
    >
      <IdentityPanels lng={lng} hook={hook} />
    </SettingsSection>
  );
}
