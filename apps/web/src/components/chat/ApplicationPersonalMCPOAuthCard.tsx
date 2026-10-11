'use client';

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useApplicationPersonalMCPOAuth } from '@/hooks/useApplicationPersonalMCPOAuth';
import { personalMCPOAuthMessage } from '@/lib/application-personal-mcp-oauth';
import type { ApplicationCommandStatus } from '@/types/application-commands';

interface Props { status: ApplicationCommandStatus; checkResult: () => Promise<void>; readError: Error | null; }
const copy = 'settings.application_tools';

export function ApplicationPersonalMCPOAuthCard({ status, checkResult, readError }: Props) {
  const { t } = useTranslation();
  const action = useApplicationPersonalMCPOAuth(status, checkResult);
  const checkButton = useRef<HTMLButtonElement>(null);
  const busy = action.mode === 'busy';
  const actionable = action.mode !== 'uncertain' && action.mode !== 'done';
  return <section className="mt-2 w-full min-w-0 rounded-xl border bg-muted/20 p-3" aria-label={t(`${copy}.mcp_oauth_title`)} aria-busy={busy}>
    <h3 className="flex items-start gap-2 text-sm font-medium"><Server className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />{t(`${copy}.mcp_oauth_title`)}</h3>
    <p role="status" className="mt-1 break-words text-sm text-muted-foreground">{t(`${copy}.${personalMCPOAuthMessage(status, action.mode, action.expired)}`)}</p>
    <div className="mt-2 flex flex-wrap gap-2">
      {action.waiting && actionable && <Button size="sm" aria-disabled={busy || action.mode === 'started'} onClick={() => { if (!busy) void action.start(); }}>{t(`${copy}.mcp_oauth_open`)}</Button>}
      {action.resuming && actionable && <Button size="sm" aria-disabled={busy} onClick={() => {
        if (!busy) void action.complete(() => checkButton.current?.focus());
      }}>{t(`${copy}.mcp_oauth_complete`)}</Button>}
      <Button ref={checkButton} size="sm" variant="outline" aria-disabled={busy} onClick={() => { if (!busy) void checkResult(); }}>{t(`${copy}.secure_check`)}</Button>
    </div>
    {readError && <p role="alert" className="mt-2 text-sm text-destructive">{t(`${copy}.secure_read_failed`)}</p>}
  </section>;
}
