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
  enforced_on_routes: boolean;
  updated_by: string | null;
  updated_at: string | null;
  is_default: boolean;
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

      <div className="space-y-3">
        {(capabilities ?? []).map(capability => {
          const switchId = `capability-${capability.capability}`;
          const blockedByDeployment = !capability.deployment_available;
          return (
            <div
              key={capability.capability}
              className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex-1 space-y-1">
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
                <p className="text-xs text-muted-foreground">
                  {t(`${capability.label_key}_description`)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {blockedByDeployment
                    ? t('settings.admin.capabilities.deploymentBlocked')
                    : capability.enforced_in_catalogue && capability.enforced_on_routes
                      ? t('settings.admin.capabilities.enforcedBoth')
                      : capability.enforced_in_catalogue
                        ? t('settings.admin.capabilities.enforcedCatalogue')
                        : t('settings.admin.capabilities.enforcedRoutes')}
                </p>
              </div>
              <Switch
                id={switchId}
                checked={capability.switch_enabled}
                disabled={saving || blockedByDeployment}
                onCheckedChange={checked => void handleToggle(capability, checked)}
                aria-label={t(capability.label_key)}
              />
            </div>
          );
        })}
      </div>
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
