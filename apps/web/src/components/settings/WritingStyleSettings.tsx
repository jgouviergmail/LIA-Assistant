'use client';

import { type ReactNode, useId, useRef, useState } from 'react';

import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { InfoBox } from '@/components/ui/info-box';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { useAuth } from '@/hooks/useAuth';
import { useWritingStyle } from '@/hooks/useWritingStyle';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { Feather, Trash2 } from '@/lib/icons';
import type { BaseSettingsProps } from '@/types/settings';
import type { WritingStyle } from '@/types/writing-style';

const PREFIX = 'settings.writing_style';

/** What the section says of what was learned: one sentence per state (pure). */
export type WritingStyleState = 'learned' | 'too_few' | 'nothing_yet' | 'off_nothing';

export function writingStyleState(style: WritingStyle): WritingStyleState {
  if (style.profile !== null) return 'learned';
  if (style.learned_at !== null) return 'too_few';
  return style.enabled ? 'nothing_yet' : 'off_nothing';
}

function formatDay(iso: string | null, lng: Language, timeZone: string | undefined): string {
  if (!iso) return '';
  return new Intl.DateTimeFormat(getIntlLocale(lng), { dateStyle: 'long', timeZone }).format(
    new Date(iso)
  );
}

/**
 * Writing style — LIA writes the person's e-mails the way they write them (ADR-383).
 *
 * The switch, what LIA learned from the latest sent e-mails (shown in clear: it is the
 * person's own record) with when it is learned again, and forgetting it. The first load
 * is a skeleton; a save or a forget keeps the section mounted (`aria-busy`), and the
 * switch keeps its focus while it saves (`aria-disabled`, guarded in the handler).
 * Forgetting removes the button that asked for it, so the focus goes back to the switch.
 */
export function WritingStyleSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const toast = useApplicationAccountToast(user?.id);
  const { style, error, refetch, setEnabled, forget, saving, forgetting } = useWritingStyle();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const switchRef = useRef<HTMLButtonElement>(null);
  const labelId = useId();
  const hintId = useId();

  const toggle = async (next: boolean) => {
    if (saving) return;
    const saved = await setEnabled(next);
    if (saved) toast.success(t(next ? `${PREFIX}.switched_on` : `${PREFIX}.switched_off`));
    else toast.error(t('common.error'));
  };

  const confirmForget = async () => {
    if (forgetting) return;
    const forgotten = await forget();
    setConfirmOpen(false);
    if (forgotten) {
      toast.success(t(`${PREFIX}.forgotten`));
      switchRef.current?.focus();
    } else {
      toast.error(t('common.error'));
    }
  };

  let body: ReactNode;
  if (style === undefined) {
    body = error ? (
      <InfoBox variant="error" className="flex items-center justify-between gap-3">
        <p className="text-sm">{t(`${PREFIX}.load_error`)}</p>
        <Button variant="outline" size="sm" onClick={refetch}>
          {t('common.retry')}
        </Button>
      </InfoBox>
    ) : (
      <Skeleton className="h-24 w-full" label={t('common.loading')} />
    );
  } else {
    const state = writingStyleState(style);
    const dates = {
      count: style.mails_read ?? 0,
      date: formatDay(style.learned_at, lng, user?.timezone),
      renews: formatDay(style.renews_at, lng, user?.timezone),
    };
    body = (
      <div className="space-y-4" aria-busy={saving || forgetting}>
        <Card
          surface="nested"
          variant="flat"
          className="flex items-center justify-between gap-3 p-3"
        >
          <div className="flex-1">
            <p id={labelId} className="text-sm font-medium">
              {t(`${PREFIX}.enable`)}
            </p>
            <p id={hintId} className="text-xs text-muted-foreground">
              {t(`${PREFIX}.enable_hint`)}
            </p>
          </div>
          <Switch
            ref={switchRef}
            checked={style.enabled}
            onCheckedChange={next => void toggle(next)}
            aria-labelledby={labelId}
            aria-describedby={hintId}
            aria-disabled={saving}
          />
        </Card>

        {state === 'learned' ? (
          <div className="space-y-2">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <Feather className="h-4 w-4 text-primary" aria-hidden="true" />
              {t(`${PREFIX}.learned_heading`)}
            </h3>
            <p className="whitespace-pre-line rounded-lg border bg-background p-3 text-sm">
              {style.profile}
            </p>
            <p className="text-xs text-muted-foreground">{t(`${PREFIX}.learned_meta`, dates)}</p>
            {!style.enabled ? (
              <p className="text-xs text-muted-foreground">{t(`${PREFIX}.off_kept`)}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t(`${PREFIX}.${state}`, dates)}</p>
        )}

        {style.learned_at !== null ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setConfirmOpen(true)}
            isLoading={forgetting}
          >
            <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
            {t(`${PREFIX}.forget`)}
          </Button>
        ) : null}

        <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t(`${PREFIX}.forget_title`)}</AlertDialogTitle>
              <AlertDialogDescription>{t(`${PREFIX}.forget_description`)}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={() => void confirmForget()}>
                <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
                {t(`${PREFIX}.forget`)}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  return (
    <SettingsSection
      value="writing-style"
      title={t('settings.writing_style.title')}
      description={t('settings.writing_style.description')}
      icon={Feather}
    >
      {body}
    </SettingsSection>
  );
}
