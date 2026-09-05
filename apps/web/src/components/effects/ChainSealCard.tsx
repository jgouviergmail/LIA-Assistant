'use client';

/**
 * ChainSealCard — what the registers can PROVE (ADR-263, lot 5).
 *
 * One card above both tabs, not one per register: a single chain seals the two
 * journals, and two indicators saying the same thing would invite the reader to
 * believe they were checked separately.
 *
 * The card never claims more than it knows, and that shapes every line of it:
 *
 * - on opening it states the SEAL — how much is sealed, up to when, how much is
 *   not yet. It says nothing about integrity, because nothing was checked.
 * - « intact » appears only after the reader runs the verification, and only
 *   for what the walk actually covered. The rows sealed after the last link are
 *   named beside it rather than folded into the verdict.
 * - a failed check clears the verdict rather than leaving the previous one on
 *   screen.
 *
 * The head fingerprint is shown because it is the ONE thing a person can do
 * alone: noting it and comparing it later detects a rewrite even by someone
 * able to alter a row and its sealing entry together.
 *
 * Split into three pieces — the shell, the seal, the verdict — because they are
 * three different claims, and because one component holding all their branches
 * is exactly the hotspot the complexity ratchet refuses.
 */

import { AlertTriangle, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert, AlertContent, AlertDescription, AlertIcon } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useChainSeal, type ChainSeal, type ChainVerdict } from '@/hooks/useChainSeal';
import { getIntlLocale, type Language } from '@/i18n/settings';

export function ChainSealCard() {
  const { t, i18n } = useTranslation();
  const { seal, verdict, loading, verifying, error, verify } = useChainSeal();
  const locale = getIntlLocale(i18n.language as Language);
  const sealFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeStyle: 'short' }),
    [locale]
  );

  // A skeleton of the real geometry rather than nothing: the card sits above
  // the tabs, so appearing late would push the whole journal down under the
  // reader's pointer.
  if (loading || !seal) {
    return (
      <Card>
        <CardContent className="p-4">
          <Skeleton className="h-10 w-full" label={t('registers.seal.loading')} />
        </CardContent>
      </Card>
    );
  }

  // Switched off is a legitimate configuration, and saying so is the honest
  // alternative to a card that reads « nothing sealed » as if something failed.
  if (!seal.sealing_enabled) {
    return (
      <Card>
        <CardContent className="flex items-start gap-3 p-4 text-sm text-muted-foreground">
          <ShieldQuestion className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
          <p>{t('registers.seal.disabled')}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SealSummary
            seal={seal}
            broken={verdict?.ok === false}
            formatDate={value => sealFormat.format(new Date(value))}
          />

          <Button
            variant="outline"
            size="sm"
            onClick={() => void verify()}
            isLoading={verifying}
            loadingText={t('registers.seal.verifying')}
          >
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {t('registers.seal.verify')}
          </Button>
        </div>

        {/* The verdict announces itself: `Alert` is already a live region, so
            wrapping it in a second one would nest two and make a screen reader
            read the outcome twice. */}
        <div className="space-y-2">
          <SealVerdict verdict={verdict} error={error} />
        </div>
      </CardContent>
    </Card>
  );
}

interface SealSummaryProps {
  seal: ChainSeal;
  /** Whether a verification has already failed — it changes the icon, only. */
  broken: boolean;
  formatDate: (value: string) => string;
}

/** What is sealed, and what is not yet. No integrity claim lives here. */
function SealSummary({ seal, broken, formatDate }: SealSummaryProps) {
  const { t } = useTranslation();

  return (
    <div className="flex min-w-0 items-start gap-3">
      {broken ? (
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
      ) : (
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
      )}
      <div className="min-w-0 space-y-1">
        <p className="text-sm font-medium">
          {seal.entries === 0
            ? t('registers.seal.not_yet')
            : t('registers.seal.sealed_until', { date: formatDate(seal.sealed_until ?? '') })}
        </p>
        {seal.pending > 0 && (
          <p className="text-xs text-muted-foreground">
            {t('registers.seal.pending', { count: seal.pending })}
          </p>
        )}
      </div>
    </div>
  );
}

interface SealVerdictProps {
  verdict: ChainVerdict | undefined;
  error: Error | null;
}

/** The outcome of an actual walk — nothing at all until one has run. */
function SealVerdict({ verdict, error }: SealVerdictProps) {
  const { t } = useTranslation();

  if (error) {
    return (
      <Alert variant="error">
        <AlertIcon variant="error" />
        <AlertContent>
          <AlertDescription>{t('registers.seal.verify_failed')}</AlertDescription>
        </AlertContent>
      </Alert>
    );
  }

  if (!verdict) {
    return null;
  }

  if (!verdict.ok) {
    return (
      <Alert variant="error">
        <AlertIcon variant="error" />
        <AlertContent>
          <AlertDescription>
            {t('registers.seal.verdict_broken', { seq: verdict.broken_at_seq ?? 0 })}
          </AlertDescription>
        </AlertContent>
      </Alert>
    );
  }

  return (
    <Alert variant="success">
      <AlertIcon variant="success" />
      {/* The fingerprint is a SIBLING of the sentence, not a child of it:
          `AlertDescription` renders a <p>, and the 64 characters need their own
          block to wrap on a phone without stretching the card. */}
      <AlertContent className="min-w-0 space-y-1">
        <AlertDescription>
          {t('registers.seal.verdict_ok', { count: verdict.payloads_checked })}
        </AlertDescription>
        {verdict.head_hash && (
          <p className="break-all font-mono text-xs opacity-80">
            {t('registers.seal.fingerprint')} {verdict.head_hash}
          </p>
        )}
      </AlertContent>
    </Alert>
  );
}
