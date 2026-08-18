'use client';

import { useCallback } from 'react';
import { toast } from 'sonner';
import { ExternalLink, Globe } from 'lucide-react';

import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';

import type { BaseSettingsProps } from '@/types/settings';

const PUBLIC_DEMO_LINK_ENDPOINT = '/admin/public-demo-link';

/** The demonstrator link as the admin API reports it. */
export interface PublicDemoLinkAdminView {
  /** Whether visitors are currently shown the link. */
  enabled: boolean;
  /** Where it points when live; null otherwise. */
  url: string | null;
  /** Whether this deployment declares a demonstrator URL at all. */
  url_configured: boolean;
}

const SWITCH_ID = 'public-demo-link-switch';

/**
 * Show or hide the public demonstrator link.
 *
 * This is the control an operator reaches for during an incident, so it takes
 * effect immediately and states the deployment fact: a switch on an instance
 * that declares no demonstrator URL would flip a setting nobody can see, and
 * the card says that rather than letting the operator believe it worked.
 */
export default function AdminPublicDemoLinkSection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  const { data, loading, setData } = useApiQuery<PublicDemoLinkAdminView>(
    PUBLIC_DEMO_LINK_ENDPOINT,
    {
      componentName: 'AdminPublicDemoLinkSection',
      initialData: { enabled: false, url: null, url_configured: false },
    }
  );

  const { mutate, loading: saving } = useApiMutation<
    { enabled: boolean },
    PublicDemoLinkAdminView
  >({ method: 'PUT', componentName: 'AdminPublicDemoLinkSection' });

  const handleToggle = useCallback(
    async (checked: boolean) => {
      try {
        const updated = await mutate(PUBLIC_DEMO_LINK_ENDPOINT, { enabled: checked });
        setData(previous => updated ?? previous);
        toast.success(
          checked
            ? t('settings.admin.publicDemoLink.enabledSuccess')
            : t('settings.admin.publicDemoLink.disabledSuccess')
        );
      } catch {
        toast.error(t('settings.admin.publicDemoLink.error'));
      }
    },
    [mutate, setData, t]
  );

  const deployed = data?.url_configured ?? false;

  const content = loading ? (
    <div aria-busy="true">
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>
  ) : (
    <div className="space-y-4">
      <InfoBox>{t('settings.admin.publicDemoLink.intro')}</InfoBox>

      <div className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex-1 space-y-1">
          <Label htmlFor={SWITCH_ID} className="text-sm font-medium">
            {t('settings.admin.publicDemoLink.switchLabel')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {deployed
              ? t('settings.admin.publicDemoLink.switchHint')
              : t('settings.admin.publicDemoLink.notDeployed')}
          </p>
          {data?.enabled && data.url && (
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs underline underline-offset-4 hover:text-foreground"
            >
              {data.url}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          )}
        </div>
        <Switch
          id={SWITCH_ID}
          checked={data?.enabled ?? false}
          disabled={saving || !deployed}
          onCheckedChange={checked => void handleToggle(checked)}
          aria-label={t('settings.admin.publicDemoLink.switchLabel')}
        />
      </div>
    </div>
  );

  return (
    <SettingsSection
      value="admin-public-demo-link"
      title={t('settings.admin.publicDemoLink.title')}
      description={t('settings.admin.publicDemoLink.description')}
      icon={Globe}
    >
      {content}
    </SettingsSection>
  );
}
