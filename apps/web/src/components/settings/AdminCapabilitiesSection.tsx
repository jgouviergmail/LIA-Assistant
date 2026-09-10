'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';
import { SlidersHorizontal } from 'lucide-react';

import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';

import type { BaseSettingsProps } from '@/types/settings';

const CAPABILITIES_ENDPOINT = '/admin/capabilities';

/** One capability as the admin API reports it. */
export interface CapabilitySwitch {
  capability: string;
  label_key: string;
  /** What the operator set. */
  switch_enabled: boolean;
  /** What the deployment (environment) permits at all. */
  deployment_available: boolean;
  /** What the runtime enforces: switch AND deployment. */
  effective_enabled: boolean;
  enforced_in_catalogue: boolean;
  /** A route dependency refuses it. */
  enforced_on_routes: boolean;
  /**
   * An internal chokepoint refuses it — speech synthesis, memory extraction,
   * the sandbox. Split from `enforced_on_routes` in B7, which used to carry
   * both and told an operator a service gate was a route.
   */
  enforced_in_service?: boolean;
  /** Which group the panel draws it in; declared by the backend spec. */
  family?: string;
  updated_by: string | null;
  updated_at: string | null;
  is_default: boolean;
}

/**
 * The order the panel draws its families in.
 *
 * The DECLARATION's order, never the payload's: an operator who switched
 * something must find the panel where they left it. A family the backend sends
 * that is not listed here is drawn last rather than dropped — an invisible
 * switch is worse than a misplaced one.
 */
const FAMILY_ORDER: readonly string[] = [
  'media',
  'knowledge',
  'reach',
  'work',
  'people',
  'assistant',
];

/**
 * Group the switches by family, in the declared order.
 *
 * @param rows - What the admin API returned.
 * @returns One entry per non-empty family, families in `FAMILY_ORDER` first
 *   and any unknown one after, each keeping the payload's own order inside.
 */
function groupByFamily(rows: readonly CapabilitySwitch[]): [string, CapabilitySwitch[]][] {
  const byFamily = new Map<string, CapabilitySwitch[]>();
  for (const row of rows) {
    const family = row.family ?? 'assistant';
    const bucket = byFamily.get(family);
    if (bucket) bucket.push(row);
    else byFamily.set(family, [row]);
  }
  const known = FAMILY_ORDER.filter(family => byFamily.has(family));
  const unknown = [...byFamily.keys()].filter(family => !FAMILY_ORDER.includes(family));
  return [...known, ...unknown].map(family => [family, byFamily.get(family) ?? []]);
}

/**
 * Where a switch actually bites, in one sentence.
 *
 * @param capability - The row.
 * @param t - The caller's translator.
 * @returns The sentence the row carries under its description.
 */
function enforcementLine(
  capability: CapabilitySwitch,
  t: (key: string) => string
): string {
  const prefix = 'settings.admin.capabilities.';
  if (!capability.deployment_available) return t(`${prefix}deploymentBlocked`);
  if (capability.enforced_in_catalogue && capability.enforced_on_routes) {
    return t(`${prefix}enforcedBoth`);
  }
  if (capability.enforced_in_catalogue) return t(`${prefix}enforcedCatalogue`);
  // Split in B7: five capabilities are enforced at an internal chokepoint, and
  // saying « routes » about them told an operator something untrue.
  if (capability.enforced_on_routes) return t(`${prefix}enforcedRoutes`);
  return t(`${prefix}enforcedService`);
}

/** One switch: what it is, where it bites, and whether it can move. */
function CapabilityRow({
  capability,
  saving,
  onToggle,
  t,
}: {
  capability: CapabilitySwitch;
  saving: boolean;
  onToggle: (capability: CapabilitySwitch, checked: boolean) => Promise<void>;
  t: (key: string) => string;
}) {
  const switchId = `capability-${capability.capability}`;
  const blockedByDeployment = !capability.deployment_available;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor={switchId} className="text-sm font-medium">
            {t(capability.label_key)}
          </Label>
          {blockedByDeployment && (
            <Badge variant="secondary">
              {t('settings.admin.capabilities.unavailableBadge')}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{t(`${capability.label_key}_description`)}</p>
        <p className="text-xs text-muted-foreground">{enforcementLine(capability, t)}</p>
      </div>
      <Switch
        id={switchId}
        checked={capability.switch_enabled}
        disabled={saving || blockedByDeployment}
        onCheckedChange={checked => void onToggle(capability, checked)}
        aria-label={t(capability.label_key)}
      />
    </div>
  );
}

/**
 * Instance-wide capability switches (speech, images, documents, browser…).
 *
 * The panel shows what is ENFORCED, not only what was toggled: a capability
 * the deployment forbids keeps its switch visible but inert, and says so.
 * Hiding that distinction would let an operator flip a switch and believe
 * something changed.
 */
export default function AdminCapabilitiesSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  const {
    data: capabilities,
    loading,
    setData,
  } = useApiQuery<CapabilitySwitch[]>(CAPABILITIES_ENDPOINT, {
    componentName: 'AdminCapabilitiesSection',
    initialData: [],
  });

  const { mutate, loading: saving } = useApiMutation<{ enabled: boolean }, CapabilitySwitch>({
    method: 'PUT',
    componentName: 'AdminCapabilitiesSection',
  });

  const handleToggle = useCallback(
    async (capability: CapabilitySwitch, checked: boolean) => {
      try {
        const updated = await mutate(`${CAPABILITIES_ENDPOINT}/${capability.capability}`, {
          enabled: checked,
        });
        setData(previous =>
          (previous ?? []).map(row =>
            row.capability === capability.capability ? (updated ?? row) : row
          )
        );
        toast.success(
          checked
            ? t('settings.admin.capabilities.enabledSuccess')
            : t('settings.admin.capabilities.disabledSuccess')
        );
      } catch {
        toast.error(t('settings.admin.capabilities.error'));
      }
    },
    [mutate, setData, t]
  );

  const content = loading ? (
    <div className="space-y-3" aria-busy="true">
      {[0, 1, 2].map(index => (
        <Skeleton key={index} className="h-20 w-full rounded-lg" />
      ))}
    </div>
  ) : (
    <div className="space-y-4">
      <InfoBox>{t('settings.admin.capabilities.intro')}</InfoBox>

      {groupByFamily(capabilities ?? []).map(([family, rows]) => (
        <section
          key={family}
          role="group"
          data-family={family}
          aria-label={t(`settings.admin.capabilities.families.${family}`)}
          className="space-y-3"
        >
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t(`settings.admin.capabilities.families.${family}`)}
          </h3>
          {rows.map(capability => (
            <CapabilityRow
              key={capability.capability}
              capability={capability}
              saving={saving}
              onToggle={handleToggle}
              t={t}
            />
          ))}
        </section>
      ))}
    </div>
  );

  return (
    <SettingsSection
      value="admin-capabilities"
      title={t('settings.admin.capabilities.title')}
      description={t('settings.admin.capabilities.description')}
      icon={SlidersHorizontal}
    >
      {content}
    </SettingsSection>
  );
}
