'use client';

/**
 * Verifying the registers of one, several or every account (ADR-263, lot 5).
 *
 * It sits inside the extraction section and reuses the scope the operator has
 * already expressed there: the accounts chosen for an export are the accounts
 * whose integrity they are asking about. A second account picker would be a
 * second place for the two to disagree.
 *
 * Three properties this surface owes:
 *
 * - **Nothing runs on opening.** A deep walk over every chain is a batch job,
 *   not a page load, and a verdict shown before anyone asked for one is a
 *   claim nobody made.
 * - **Broken first.** The API returns failures ahead of the rest for a reason;
 *   this preserves that order rather than sorting by account.
 * - **The cap is stated.** A sweep is bounded, so fifty green rows must never
 *   read as an answer about five hundred accounts: the result says how many
 *   accounts were checked out of how many hold a chain (ADR-185).
 * - **A failed call clears the result.** Leaving a green list on screen after
 *   an error is the one lie an audit surface must never tell.
 *
 * No audit-log entry and no unmasking switch, unlike the export beside it: a
 * verdict says whether rows were altered, never what any of them says.
 */

import { useCallback, useState } from 'react';
import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { UserSuggestion } from '@/components/settings/AdminUserAutocomplete';
import { Alert, AlertContent, AlertDescription, AlertIcon } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';

/** One account's verdict, as the administrator sweep returns it. */
export interface AdminChainStatus {
  user_id: string;
  ok: boolean;
  entries: number;
  pending: number;
  payloads_checked: number;
  broken_at_seq: number | null;
  reason: string | null;
}

/** What a sweep covered — and what it did not reach. */
export interface AdminChainSweep {
  rows: AdminChainStatus[];
  accounts_checked: number;
  accounts_with_chain: number;
  limit: number;
}

export interface AdminChainVerificationProps {
  /** The accounts the operator picked; empty means every account. */
  users: UserSuggestion[];
}

export function AdminChainVerification({ users }: AdminChainVerificationProps) {
  const { t } = useTranslation();
  const [sweep, setSweep] = useState<AdminChainSweep | undefined>(undefined);
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState(false);

  const verify = useCallback(async () => {
    setRunning(true);
    setFailed(false);
    try {
      const query = users.map(user => `user_ids=${encodeURIComponent(user.id)}`).join('&');
      setSweep(
        await apiClient.get<AdminChainSweep>(
          `/admin/effects/chain/verify?deep=true${query ? `&${query}` : ''}`
        )
      );
    } catch (caught) {
      setSweep(undefined);
      setFailed(true);
      logger.error(
        'AdminChainVerification: sweep failed',
        caught instanceof Error ? caught : new Error(String(caught))
      );
    } finally {
      setRunning(false);
    }
  }, [users]);

  const broken = sweep?.rows.filter(row => !row.ok) ?? [];
  const partial = sweep !== undefined && sweep.accounts_checked < sweep.accounts_with_chain;

  return (
    <div className="space-y-3 border-t pt-6">
      <div className="space-y-1">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('settings.admin.registers.verify_title')}
        </h3>
        <p className="text-xs text-muted-foreground">
          {users.length === 0
            ? t('settings.admin.registers.verify_hint_all')
            : t('settings.admin.registers.verify_hint_selected', { count: users.length })}
        </p>
      </div>

      <Button
        variant="outline"
        onClick={() => void verify()}
        isLoading={running}
        loadingText={t('settings.admin.registers.verify_running')}
      >
        <ShieldCheck className="h-4 w-4" aria-hidden="true" />
        {t('settings.admin.registers.verify_action')}
      </Button>

      {/* `Alert` is already a live region; a second one around it would make a
          screen reader announce the outcome twice. */}
      <div className="space-y-2">
        {failed && (
          <Alert variant="error">
            <AlertIcon variant="error" />
            <AlertContent>
              <AlertDescription>{t('settings.admin.registers.verify_failed')}</AlertDescription>
            </AlertContent>
          </Alert>
        )}

        {sweep && broken.length === 0 && (
          <Alert variant="success">
            <AlertIcon variant="success" />
            <AlertContent>
              <AlertDescription>
                {t('settings.admin.registers.verify_all_ok', { count: sweep.accounts_checked })}
              </AlertDescription>
            </AlertContent>
          </Alert>
        )}

        {partial && sweep && (
          <p className="text-xs text-muted-foreground">
            {t('settings.admin.registers.verify_partial', {
              checked: sweep.accounts_checked,
              total: sweep.accounts_with_chain,
            })}
          </p>
        )}

        {broken.length > 0 && (
          <Alert variant="error">
            <AlertIcon variant="error" />
            {/* The list is a SIBLING of the sentence: `AlertDescription`
                renders a <p>, and a <ul> inside one is invalid HTML — the
                browser closes the paragraph early and the layout breaks. */}
            <AlertContent className="min-w-0 space-y-2">
              <AlertDescription>
                {t('settings.admin.registers.verify_broken', { count: broken.length })}
              </AlertDescription>
              <ul className="space-y-1">
                {broken.map(row => (
                  <li key={row.user_id} className="flex items-start gap-2 font-mono text-xs">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                    <span className="break-all">
                      {row.user_id} — {row.reason ?? '?'} @ {row.broken_at_seq ?? '?'}
                    </span>
                  </li>
                ))}
              </ul>
            </AlertContent>
          </Alert>
        )}
      </div>
    </div>
  );
}
