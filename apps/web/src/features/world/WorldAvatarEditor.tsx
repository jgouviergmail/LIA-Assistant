'use client';
import { useEffect, useRef, useState } from 'react';
import { UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api-client';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { DEFAULT_AVATAR, appearanceSignature } from './avatar-catalogue';
import type { AvatarView, AvatarWrite } from './avatar-protocol';
import { WorldAvatarFields } from './WorldAvatarFields';

interface Props {
  lng: Language;
  initial: AvatarView;
  onboarding?: boolean;
  saving: boolean;
  save(value: AvatarWrite): Promise<AvatarView | null>;
  refresh(): Promise<void>;
  onSaved(value: AvatarView): void;
  onCancel?(): void;
}
export function WorldAvatarEditor(props: Props) {
  const { lng, initial, onboarding = false, saving, save, onSaved } = props;
  const { t } = useTranslation(lng);
  const [basis] = useState(initial);
  const [appearance, setAppearance] = useState(initial.preferences.appearance);
  const [consent, setConsent] = useState(!onboarding);
  const [error, setError] = useState<'conflict' | 'failed' | null>(null);
  const [reset, setReset] = useState(initial.needs_reset);
  const revision = basis.preferences.revision;
  const lifetime = useRef(0);
  useEffect(
    () => () => {
      lifetime.current++;
    },
    []
  );
  const changed =
    appearanceSignature(appearance) !== appearanceSignature(basis.preferences.appearance);
  async function submit() {
    if (!consent || saving) return;
    const turn = lifetime.current;
    setError(null);
    try {
      const accepted = await save({
        expected_revision: revision,
        appearance,
        consent: true,
        reset,
      });
      if (accepted && turn === lifetime.current) onSaved(accepted);
    } catch (failure) {
      if (turn === lifetime.current)
        setError(failure instanceof ApiError && failure.status === 409 ? 'conflict' : 'failed');
    }
  }
  return (
    <form
      className="space-y-4"
      aria-busy={saving}
      onSubmit={event => {
        event.preventDefault();
        void submit();
      }}
    >
      <div
        className="flex min-h-11 items-center gap-2 rounded-xl border bg-muted/30 px-3 text-sm"
        data-world-public-name
      >
        <UserRound className="size-4 shrink-0 text-primary" aria-hidden="true" />
        <span className="truncate font-medium">{initial.public_name}</span>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{t('world.avatar.name_hint')}</p>
      <fieldset aria-disabled={saving} className="min-w-0">
        <WorldAvatarFields
          lng={lng}
          appearance={appearance}
          onChange={value => {
            if (!saving) setAppearance(value);
          }}
        />
      </fieldset>
      {initial.needs_reset && (
        <p role="status" className="rounded-xl border border-amber-500/40 p-3 text-sm">
          {t('world.avatar.needs_reset')}
        </p>
      )}
      {onboarding && (
        <label className="flex items-start gap-3 text-sm leading-relaxed">
          <input
            name="world-presence-consent"
            type="checkbox"
            className="mt-1 size-5 shrink-0 accent-primary"
            checked={consent}
            aria-disabled={saving}
            onChange={event => {
              if (!saving) setConsent(event.target.checked);
            }}
            aria-label={t('world.session.consent')}
          />
          {t('world.avatar.consent')}
        </label>
      )}
      {error && (
        <div role="alert" className="space-y-2 rounded-xl border border-destructive/40 p-3 text-sm">
          <p>{t('world.avatar.' + error)}</p>
          {error === 'conflict' && (
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              onClick={() => {
                void props.refresh().catch(() => setError('failed'));
              }}
            >
              {t('world.home.reload')}
            </Button>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          className="min-h-11"
          aria-disabled={saving}
          onClick={() => {
            if (saving) return;
            setAppearance(DEFAULT_AVATAR);
            setReset(true);
          }}
        >
          {t('world.avatar.defaults')}
        </Button>
        <div className="ml-auto flex gap-2">
          {props.onCancel && (
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              aria-disabled={saving}
              onClick={() => {
                if (!saving) props.onCancel?.();
              }}
            >
              {t('world.home.cancel')}
            </Button>
          )}
          <Button
            type="submit"
            className="min-h-11"
            disabled={!consent || (!onboarding && !changed && !reset)}
            aria-disabled={saving}
          >
            {t(onboarding ? 'world.session.enter' : 'world.home.save')}
          </Button>
        </div>
      </div>
    </form>
  );
}
