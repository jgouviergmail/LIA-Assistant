'use client';

import Link from 'next/link';
import { type ReactNode, useId, useRef } from 'react';

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
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { useAuth } from '@/hooks/useAuth';
import { useWritingStyle, type WritingStyleLearnResult } from '@/hooks/useWritingStyle';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { Feather, RefreshCw, Trash2 } from '@/lib/icons';
import { settingsSectionHref } from '@/lib/settings-sections';
import { workbenchRefusal } from '@/lib/workbench/errors';
import type { LLMUsage } from '@/types/llm-usage';
import type { BaseSettingsProps } from '@/types/settings';
import type { WritingStyle, WritingStyleLearningOutcome } from '@/types/writing-style';

const PREFIX = 'settings.writing_style';
/** A mailbox refusing LIA's access while it is read: the `reconnect` outcome's situation. */
const RECONNECT_REFUSAL = 'workbench.errors.reconnect_required';

/** What the section says of what was learned: one sentence per state (pure). */
export type WritingStyleState = 'learned' | 'too_few' | 'nothing_yet' | 'off_nothing';

export function writingStyleState(style: WritingStyle): WritingStyleState {
  if (style.profile !== null) return 'learned';
  if (style.learned_at !== null) return 'too_few';
  return style.enabled ? 'nothing_yet' : 'off_nothing';
}

/** What the section says once a learning ends. */
export interface LearningNotice {
  tone: 'default' | 'warning' | 'error';
  /** The i18n key of its sentence, and the figures that sentence quotes. */
  key: string;
  values?: Record<string, number>;
  /** A mailbox must be connected or reconnected: the notice leads to the connectors. */
  toConnectors: boolean;
  /** What the learning cost, when it spent anything now. */
  usage: LLMUsage | null;
}

const OUTCOMES: Readonly<
  Record<WritingStyleLearningOutcome, Pick<LearningNotice, 'tone' | 'toConnectors'>>
> = {
  learned: { tone: 'default', toConnectors: false },
  too_few: { tone: 'default', toConnectors: false },
  no_mailbox: { tone: 'warning', toConnectors: true },
  reconnect: { tone: 'warning', toConnectors: true },
  switched_off: { tone: 'default', toConnectors: false },
  superseded: { tone: 'default', toConnectors: false },
};

/**
 * The notice a learning leaves (pure). Every outcome the API names has its sentence; a
 * refusal is said in the workbench's words — a mailbox refusing LIA's access in the
 * section's own, the situation of the `reconnect` outcome — and anything else as the
 * generic error.
 */
export function learningNotice(result: WritingStyleLearnResult): LearningNotice {
  if (result.answered) {
    const { outcome, usage } = result.learning;
    return { ...OUTCOMES[outcome], key: `${PREFIX}.outcome.${outcome}`, usage };
  }
  const refusal = workbenchRefusal(result.error);
  if (refusal?.key === RECONNECT_REFUSAL) {
    return { ...OUTCOMES.reconnect, key: `${PREFIX}.outcome.reconnect`, usage: null };
  }
  return {
    tone: 'error',
    key: refusal?.key ?? 'common.error',
    values: refusal?.values,
    toConnectors: false,
    usage: null,
  };
}

function formatDay(iso: string | null, lng: Language, timeZone: string | undefined): string {
  if (!iso) return '';
  return new Intl.DateTimeFormat(getIntlLocale(lng), { dateStyle: 'long', timeZone }).format(
    new Date(iso)
  );
}

interface StyleRecordProps {
  style: WritingStyle;
  lng: Language;
  timeZone: string | undefined;
}

/** What was learned, shown in clear (the person's own record), or why nothing is. */
function StyleRecord({ style, lng, timeZone }: StyleRecordProps) {
  const { t } = useTranslation(lng);
  const state = writingStyleState(style);
  const facts = { count: style.mails_read ?? 0, date: formatDay(style.learned_at, lng, timeZone) };
  if (state !== 'learned') {
    return <p className="text-sm text-muted-foreground">{t(`${PREFIX}.${state}`, facts)}</p>;
  }
  return (
    <div className="space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <Feather className="h-4 w-4 text-primary" aria-hidden="true" />
        {t(`${PREFIX}.learned_heading`)}
      </h3>
      <p className="whitespace-pre-line rounded-lg border bg-background p-3 text-sm">
        {style.profile}
      </p>
      <p className="text-xs text-muted-foreground">{t(`${PREFIX}.learned_meta`, facts)}</p>
      {!style.enabled ? (
        <p className="text-xs text-muted-foreground">{t(`${PREFIX}.off_kept`)}</p>
      ) : null}
    </div>
  );
}

interface StyleActionsProps {
  lng: Language;
  enabled: boolean;
  /** Something was learned (a profile, or a learning that found too few e-mails). */
  learned: boolean;
  learning: boolean;
  forgetting: boolean;
  onLearn: () => void;
  onForget: () => void;
}

/**
 * Learning (again) and forgetting. One learn button whose label follows the record, so
 * the control the person pressed keeps its focus when « Learn my style » becomes
 * « Learn again »; none while switched off, when nothing would be read.
 */
function StyleActions({
  lng,
  enabled,
  learned,
  learning,
  forgetting,
  onLearn,
  onForget,
}: StyleActionsProps) {
  const { t } = useTranslation(lng);
  const relearnHintId = useId();
  if (!enabled && !learned) return null;
  const LearnIcon = learned ? RefreshCw : Feather;
  const relearnHint = enabled && learned;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {enabled ? (
          <Button
            size="sm"
            onClick={onLearn}
            isLoading={learning}
            loadingText={t(`${PREFIX}.learning`)}
            aria-describedby={relearnHint ? relearnHintId : undefined}
          >
            <LearnIcon className="mr-1 h-4 w-4" aria-hidden="true" />
            {t(learned ? `${PREFIX}.learn_again` : `${PREFIX}.learn`)}
          </Button>
        ) : null}
        {learned ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={onForget}
            isLoading={forgetting}
            aria-disabled={learning || undefined}
          >
            <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
            {t(`${PREFIX}.forget`)}
          </Button>
        ) : null}
      </div>
      {relearnHint ? (
        <p id={relearnHintId} className="text-xs text-muted-foreground">
          {t(`${PREFIX}.relearn_hint`)}
        </p>
      ) : null}
    </div>
  );
}

/** The sentence a learning left, where it leads, and what it cost. */
function LearningNoticeView({ notice, lng }: { notice: LearningNotice; lng: Language }) {
  const { t } = useTranslation(lng);
  return (
    <InfoBox variant={notice.tone} className="space-y-2">
      <p className="text-sm">{t(notice.key, notice.values)}</p>
      {notice.toConnectors || notice.usage ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {notice.toConnectors ? (
            <Button asChild variant="outline" size="sm">
              <Link href={settingsSectionHref(lng, 'connectors')}>
                {t(`${PREFIX}.open_connectors`)}
              </Link>
            </Button>
          ) : null}
          {notice.usage ? (
            <LLMUsageBadge usage={notice.usage} label={t(`${PREFIX}.learning_cost`)} />
          ) : null}
        </div>
      ) : null}
    </InfoBox>
  );
}

/**
 * Writing style — LIA writes the person's e-mails the way they write them (ADR-383).
 *
 * The switch, what LIA learned from the latest sent e-mails (shown in clear: it is the
 * person's own record), learning it at their click — the only moment it is learned
 * (amendment 2026-11-16) — and forgetting it. The first load is a skeleton; a save, a
 * learning or a forget keeps the section mounted (`aria-busy`). The learn button keeps
 * its focus and its place while it works (`isLoading`), and what the learning ended on
 * is said in a status region that never unmounts, with what it cost. « Forget » waits
 * for a learning in flight (`aria-disabled`, guarded in the handler): the server would
 * keep the forgetting, and the learning would have been paid for nothing — a forget
 * from elsewhere meanwhile is said as `superseded`, and what stands is read back. A
 * control that disappears hands the focus back to the switch.
 */
export function WritingStyleSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const toast = useApplicationAccountToast(user?.id);
  const { style, error, refetch, setEnabled, learn, forget, saving, learning, forgetting } =
    useWritingStyle();
  // Both belong to the account they were opened for: a learning ending after a switch of
  // account tells nothing to the next one, and a confirmation never forgets another's.
  const [confirmOpen, setConfirmOpen] = useApplicationAccountState(user?.id, false);
  const [notice, setNotice] = useApplicationAccountState<LearningNotice | null>(user?.id, null);
  const switchRef = useRef<HTMLButtonElement>(null);
  const labelId = useId();
  const hintId = useId();

  const toggle = async (next: boolean) => {
    if (saving) return;
    setNotice(null);
    const saved = await setEnabled(next);
    if (saved) toast.success(t(next ? `${PREFIX}.switched_on` : `${PREFIX}.switched_off`));
    else toast.error(t('common.error'));
  };

  const startLearning = async () => {
    if (learning) return;
    setNotice(null);
    const result = await learn();
    setNotice(learningNotice(result));
    // Switched off meanwhile: the learn button is gone, the focus goes to the switch.
    if (result.answered && result.learning.outcome === 'switched_off') {
      switchRef.current?.focus();
    }
  };

  const askForget = () => {
    if (learning) return;
    setConfirmOpen(true);
  };

  const confirmForget = async () => {
    if (forgetting) return;
    setNotice(null);
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
    body = (
      <div className="space-y-4" aria-busy={saving || learning || forgetting}>
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
              {t(`${PREFIX}.enable_hint`, { mails: style.mails_to_read })}
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

        <StyleRecord style={style} lng={lng} timeZone={user?.timezone} />

        <StyleActions
          lng={lng}
          enabled={style.enabled}
          learned={style.learned_at !== null}
          learning={learning}
          forgetting={forgetting}
          onLearn={() => void startLearning()}
          onForget={askForget}
        />

        <div role="status" aria-atomic="true">
          {notice ? <LearningNoticeView notice={notice} lng={lng} /> : null}
        </div>

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
