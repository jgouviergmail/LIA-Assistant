'use client';

import { useEffect, useId, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Key } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import {
  useApplicationAccountLifetime,
  type ApplicationAccountLifetime,
} from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import apiClient from '@/lib/api-client';
import { publishApplicationResources } from '@/lib/application-resources';
import { z } from '@/lib/zod';
import type { ApplicationCommandStatus } from '@/types/application-commands';

const response = z
  .object({
    id: z.string().uuid(),
    token: z.string().min(1),
    token_prefix: z.string().min(1),
    label: z.string().nullable(),
    created_at: z.string().datetime({ offset: true }),
  })
  .strict();
const copy = 'settings.application_tools';
interface Props {
  status: ApplicationCommandStatus;
  checkResult: () => Promise<void>;
  readError: Error | null;
}

function creationMessage(status: ApplicationCommandStatus, mode: string, expired: boolean): string {
  if (
    (mode === 'uncertain' && !status.outcome?.committed) ||
    status.outcome?.error_code === 'COMPLETION_UNKNOWN'
  )
    return 'secure_unknown';
  if (expired || status.phase === 'expired') return 'secure_expired';
  if (status.phase === 'committed' || mode === 'done') return 'secure_done';
  if (status.phase === 'failed' || status.phase === 'conflict') return 'secure_failed';
  if (mode === 'busy' || status.phase === 'claimed' || status.phase === 'resuming')
    return 'secure_running';
  return 'secure_waiting';
}

function canCreate(status: ApplicationCommandStatus, expired: boolean): boolean {
  return (
    status.operation_id === 'health_token.create' &&
    status.phase === 'waiting' &&
    status.interaction?.kind === 'device' &&
    !expired
  );
}

/** A secret is component-local only; result observation can never retrieve it again. */
export function ApplicationHealthTokenCard({ status, checkResult, readError }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const scope = user?.id ? `${user.id}:${status.command_id}` : undefined;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(scope);
  const [secret, setSecret] = useApplicationAccountState<string | null>(scope, null);
  const [mode, setMode] = useApplicationAccountState<'idle' | 'busy' | 'done' | 'uncertain'>(
    scope,
    'idle'
  );
  const [expired, setExpired] = useApplicationAccountState(scope, false);
  const inFlight = useRef<ApplicationAccountLifetime | null>(null);
  const secretInput = useRef<HTMLInputElement>(null);
  const checkButton = useRef<HTMLButtonElement>(null);
  const inputId = useId();
  useEffect(() => {
    if (secret && isCurrent()) secretInput.current?.focus();
  }, [secret, isCurrent]);
  useEffect(() => {
    const remaining = new Date(status.expires_at).getTime() - Date.now();
    setExpired(remaining <= 0);
    const timer = setTimeout(
      () => {
        setExpired(true);
      },
      Math.max(0, remaining)
    );
    return () => {
      clearTimeout(timer);
    };
  }, [setExpired, status.expires_at]);
  const waiting = canCreate(status, expired);
  async function create() {
    if (!isCurrent() || !waiting || mode !== 'idle' || inFlight.current === lifetime) return;
    inFlight.current = lifetime;
    setMode('busy');
    try {
      const created = response.parse(
        await apiClient.post<unknown>(
          `/application-commands/${encodeURIComponent(status.command_id)}/health-token`,
          {}
        )
      );
      if (!isCurrent()) return;
      setSecret(created.token);
      setMode('done');
      if (user?.id) publishApplicationResources(user.id, new Set(['health_metrics']));
      void Promise.resolve(checkResult()).catch(() => {});
    } catch {
      if (isCurrent()) setMode('uncertain');
    } finally {
      if (inFlight.current === lifetime) inFlight.current = null;
    }
  }
  const message = creationMessage(status, mode, expired);
  async function copySecret() {
    if (!secret || !isCurrent()) return;
    try {
      await navigator.clipboard.writeText(secret);
      if (isCurrent()) toast.success(t('healthMetrics.tokens.copied'));
    } catch {
      if (isCurrent()) toast.error(t('common.copyFailed'));
    }
  }
  return (
    <section
      className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3"
      aria-label={t('healthMetrics.tokens.generate')}
      aria-busy={mode === 'busy'}
    >
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <Key className="h-4 w-4 shrink-0" aria-hidden="true" />
        {t('healthMetrics.tokens.generate')}
      </h3>
      <p role="status" className="mt-1 break-words text-sm text-muted-foreground">
        {t(`${copy}.${message}`)}
      </p>
      {secret && (
        <div className="mt-2 min-w-0 space-y-2">
          <label htmlFor={inputId} className="text-sm">
            {t('healthMetrics.tokens.justCreated')}
          </label>
          <div className="flex min-w-0 gap-2">
            <Input
              ref={secretInput}
              id={inputId}
              value={secret}
              readOnly
              className="min-w-0 font-mono text-xs"
            />
            <Button
              size="icon"
              variant="outline"
              aria-label={t('common.copy')}
              onClick={() => {
                void copySecret();
              }}
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setSecret(null);
              checkButton.current?.focus();
            }}
          >
            {t('common.close')}
          </Button>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {waiting && mode === 'idle' && (
          <Button
            size="sm"
            onClick={() => {
              void create();
            }}
          >
            {t('healthMetrics.tokens.generate')}
          </Button>
        )}
        <Button
          ref={checkButton}
          size="sm"
          variant="outline"
          aria-disabled={mode === 'busy'}
          onClick={() => {
            if (mode !== 'busy') void checkResult();
          }}
        >
          {t(`${copy}.secure_check`)}
        </Button>
      </div>
      {readError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {t(`${copy}.secure_read_failed`)}
        </p>
      )}
    </section>
  );
}
