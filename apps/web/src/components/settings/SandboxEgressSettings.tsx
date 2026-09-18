'use client';

/**
 * SandboxEgressSettings — what a sandbox script may reach on the network, and
 * the permissions the person gave when asked (ADR-298).
 *
 * Two lists. « Reachable without asking »: the hosts of the person's own
 * API-key connectors (a credential travels, swapped by the proxy) and the
 * operator's allowlist — read-only, they come from elsewhere. « Your
 * permissions »: every host the person allowed from a chat question, with the
 * one thing they edit here (with or without the turn's data) and a revoke —
 * the next script that declares the host asks again. The cap is drawn as a
 * gauge because it is enforced: past it an approval holds for its run only.
 *
 * Renders nothing when the instance flag is off or the surface is unavailable
 * (the OpenLoops precedent); gated in `settings-search.ts` on the same flag.
 */

import { Globe, KeyRound, ShieldCheck, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { RowActions } from '@/components/ui/row-actions';
import { Switch } from '@/components/ui/switch';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useSandboxEgress } from '@/hooks/useSandboxEgress';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import { useTranslation } from '@/i18n/client';
import { formatInstant } from '@/lib/format-instant';
import { haptic } from '@/lib/haptics';
import type { Language } from '@/i18n/settings';
import type { EgressGrant, ReachableHost } from '@/types/sandbox-egress';
import type { BaseSettingsProps } from '@/types/settings';

/** The brand name of a connector (`CONNECTOR_LABELS`), or its raw key for one the constants do not know. */
function connectorLabel(connector: string | null): string {
  if (connector && isValidConnectorType(connector)) return CONNECTOR_LABELS[connector];
  return connector ?? '';
}

export function SandboxEgressSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const flagOn = !!config?.features?.python_sandbox_egress_enabled;
  const egress = useSandboxEgress(flagOn);

  if (!flagOn || egress.unavailable) return null;

  return (
    <SettingsSection
      value="sandbox-egress"
      title={t('settings.sandbox_egress.title')}
      description={t('settings.sandbox_egress.description')}
      icon={Globe}
    >
      {egress.loadError ? (
        <div className="flex items-center gap-3">
          <p className="text-sm text-muted-foreground">{t('common.error')}</p>
          <button
            type="button"
            onClick={() => egress.refetch()}
            className="text-sm text-primary hover:underline"
          >
            {t('common.retry')}
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          <ReachableList hosts={egress.reachable} askEnabled={egress.askEnabled} lng={lng} />
          <GrantList
            grants={egress.grants}
            total={egress.total}
            maxPerUser={egress.maxPerUser}
            lng={lng}
            setScope={egress.setScope}
            revoke={egress.revoke}
          />
        </div>
      )}
    </SettingsSection>
  );
}

function ReachableList({
  hosts,
  askEnabled,
  lng,
}: {
  hosts: ReachableHost[];
  askEnabled: boolean | null;
  lng: Language;
}) {
  const { t } = useTranslation(lng);
  return (
    <div>
      <h4 className="flex items-center gap-2 text-sm font-semibold">
        <ShieldCheck className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('settings.sandbox_egress.reachable_title')}
      </h4>
      <p className="mt-1 text-xs text-muted-foreground">
        {t('settings.sandbox_egress.reachable_description')}
      </p>
      {hosts.length === 0 ? (
        <p className="mt-2 text-sm italic text-muted-foreground">
          {t('settings.sandbox_egress.reachable_empty')}
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-border/60 rounded-xl border border-border/60">
          {hosts.map(host => (
            <li key={host.host} className="flex items-center gap-3 px-3 py-2">
              {host.status === 'connector' ? (
                <KeyRound className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              ) : (
                <Globe className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm">{host.host}</p>
                <p className="text-xs text-muted-foreground">
                  {host.status === 'connector'
                    ? t('settings.sandbox_egress.source_connector', {
                        connector: connectorLabel(host.connector),
                      })
                    : t('settings.sandbox_egress.source_operator')}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      {askEnabled === false && (
        <p className="mt-2 text-xs text-muted-foreground">
          {t('settings.sandbox_egress.ask_disabled')}
        </p>
      )}
    </div>
  );
}

function GrantList({
  grants,
  total,
  maxPerUser,
  lng,
  setScope,
  revoke,
}: {
  grants: EgressGrant[];
  total: number;
  maxPerUser: number;
  lng: Language;
  setScope: (id: string, shareTurnData: boolean) => Promise<boolean>;
  revoke: (id: string) => Promise<boolean>;
}) {
  const { t } = useTranslation(lng);
  const [busyId, setBusyId] = useState<string | null>(null);
  const notShown = Math.max(0, total - grants.length);

  const handleScope = async (grant: EgressGrant, shareTurnData: boolean) => {
    setBusyId(grant.id);
    const ok = await setScope(grant.id, shareTurnData);
    setBusyId(null);
    if (ok) haptic('confirm');
    else toast.error(t('common.error'));
  };

  const handleRevoke = async (grant: EgressGrant) => {
    setBusyId(grant.id);
    const ok = await revoke(grant.id);
    setBusyId(null);
    if (ok) {
      haptic('confirm');
      toast.success(t('settings.sandbox_egress.revoked', { host: grant.host }));
    } else toast.error(t('common.error'));
  };

  return (
    <div>
      <h4 className="flex items-center gap-2 text-sm font-semibold">
        <Globe className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t('settings.sandbox_egress.grants_title')}
      </h4>
      <p className="mt-1 text-xs text-muted-foreground">
        {t('settings.sandbox_egress.grants_description')}
      </p>
      {grants.length === 0 ? (
        <p className="mt-2 text-sm italic text-muted-foreground">
          {t('settings.sandbox_egress.grants_empty')}
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-border/60 rounded-xl border border-border/60">
          {grants.map(grant => (
            <GrantRow
              key={grant.id}
              grant={grant}
              lng={lng}
              busy={busyId === grant.id}
              onScope={share => handleScope(grant, share)}
              onRevoke={() => handleRevoke(grant)}
            />
          ))}
        </ul>
      )}
      {notShown > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {t('settings.sandbox_egress.grants_not_shown', { count: notShown })}
        </p>
      )}
      {maxPerUser > 0 && (
        <Capacity
          held={total}
          max={maxPerUser}
          label={t('settings.sandbox_egress.capacity_label')}
          text={t('settings.sandbox_egress.capacity', { held: total, max: maxPerUser })}
        />
      )}
    </div>
  );
}

function GrantRow({
  grant,
  lng,
  busy,
  onScope,
  onRevoke,
}: {
  grant: EgressGrant;
  lng: Language;
  busy: boolean;
  onScope: (shareTurnData: boolean) => void;
  onRevoke: () => void;
}) {
  const { t } = useTranslation(lng);
  const switchId = `egress-scope-${grant.id}`;
  return (
    <li className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:gap-3">
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm">{grant.host}</p>
        <p className="text-xs text-muted-foreground">
          {t('settings.sandbox_egress.granted_on', {
            date: formatInstant(grant.created_at, lng, 'short'),
          })}
          {' · '}
          {grant.last_used_at
            ? t('settings.sandbox_egress.last_used', {
                date: formatInstant(grant.last_used_at, lng, 'short'),
              })
            : t('settings.sandbox_egress.never_used')}
        </p>
      </div>
      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <label htmlFor={switchId} className="flex items-center gap-2 text-xs">
          <Switch
            id={switchId}
            checked={grant.share_turn_data}
            onCheckedChange={checked => onScope(checked)}
            aria-disabled={busy || undefined}
          />
          <span>{t('settings.sandbox_egress.with_data')}</span>
        </label>
        <RowActions
          menuLabel={t('settings.sandbox_egress.row_menu', { host: grant.host })}
          actions={[
            {
              key: 'revoke',
              label: t('settings.sandbox_egress.revoke', { host: grant.host }),
              icon: Trash2,
              tone: 'destructive',
              loading: busy,
              onSelect: onRevoke,
            },
          ]}
        />
      </div>
    </li>
  );
}

/** What the account holds against the cap the instance enforces. */
function Capacity({
  held,
  max,
  label,
  text,
}: {
  held: number;
  max: number;
  label: string;
  text: string;
}) {
  const pct = Math.min(100, Math.round((held / max) * 100));
  return (
    <div className="mt-3">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{text}</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={held}
        aria-valuemin={0}
        aria-valuemax={max}
        className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
