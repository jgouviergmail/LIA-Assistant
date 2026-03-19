'use client';

import { toast } from 'sonner';
import { Plug } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

// API endpoint constant to avoid duplication
const GLOBAL_CONFIG_ENDPOINT = '/connectors/admin/global-config';

interface ConnectorConfig {
  id: string;
  connector_type: string;
  is_enabled: boolean;
  disabled_reason: string | null;
  updated_at: string;
}

/**
 * Admin-manageable connector category keys.
 * Labels and descriptions come from i18n.
 * Only includes REAL connectors that are actually implemented in the backend.
 * Future connectors (slack, notion, github) are excluded until implemented.
 */
const ADMIN_CONNECTOR_CATEGORIES = {
  google_oauth: [
    'google_gmail',
    'google_calendar',
    'google_drive',
    'google_contacts',
    'google_tasks',
    'google_places',
  ],
  apple: ['apple_email', 'apple_calendar', 'apple_contacts'],
  microsoft_oauth: [
    'microsoft_outlook',
    'microsoft_calendar',
    'microsoft_contacts',
    'microsoft_tasks',
  ],
  google_api: ['google_routes'],
  external: ['openweathermap', 'wikipedia', 'perplexity', 'brave_search', 'browser'],
} as const;

type CategoryKey = keyof typeof ADMIN_CONNECTOR_CATEGORIES;

// Helper to safely get connector label (service names are universal, not translated)
const getConnectorLabel = (type: string): string => {
  if (isValidConnectorType(type)) {
    return CONNECTOR_LABELS[type];
  }
  return type;
};

export default function AdminConnectorsSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  // Use generic API query hook
  const {
    data: configs = [],
    loading,
    setData,
  } = useApiQuery<ConnectorConfig[]>(GLOBAL_CONFIG_ENDPOINT, {
    componentName: 'AdminConnectorsSection',
    initialData: [],
  });

  // Use generic mutation hook for updates
  const { mutate: updateConfig } = useApiMutation({
    method: 'PUT',
    componentName: 'AdminConnectorsSection',
  });

  const getConfig = (connectorType: string): ConnectorConfig | undefined => {
    return configs.find(c => c.connector_type === connectorType);
  };

  const isEnabled = (connectorType: string): boolean => {
    const config = getConfig(connectorType);
    // If no config exists, assume enabled (default behavior)
    return config ? config.is_enabled : true;
  };

  const handleToggle = async (connectorType: string, currentStatus: boolean) => {
    const action = currentStatus ? t('settings.admin.connectors.actions.disable') : t('settings.admin.connectors.actions.enable');
    let disabled_reason: string | null = null;

    if (currentStatus) {
      // Disabling - ask for reason
      disabled_reason = prompt(
        t('settings.admin.connectors.disable_prompt', { name: getConnectorLabel(connectorType) })
      );
      if (!disabled_reason) return; // User cancelled
    }

    try {
      await updateConfig(`${GLOBAL_CONFIG_ENDPOINT}/${connectorType}`, {
        is_enabled: !currentStatus,
        disabled_reason,
      });

      // Optimistic update: update local state
      setData(prev => {
        if (!prev) return prev;
        const existingConfig = prev.find(c => c.connector_type === connectorType);
        if (existingConfig) {
          // Update existing config
          return prev.map(c =>
            c.connector_type === connectorType
              ? { ...c, is_enabled: !currentStatus, disabled_reason, updated_at: new Date().toISOString() }
              : c
          );
        } else {
          // Add new config
          return [
            ...prev,
            {
              id: connectorType,
              connector_type: connectorType,
              is_enabled: !currentStatus,
              disabled_reason,
              updated_at: new Date().toISOString(),
            },
          ];
        }
      });
    } catch {
      toast.error(t('settings.admin.connectors.errors.toggle', { action: action.toLowerCase() }));
    }
  };

  // Loading state
  if (loading) {
    return (
      <SettingsSection
        value="admin-connectors"
        title={t('settings.admin.connectors.title')}
        description={t('settings.admin.connectors.description')}
        icon={Plug}
        collapsible={collapsible}
      >
        <div className="animate-pulse text-muted-foreground">{t('settings.admin.connectors.loading')}</div>
      </SettingsSection>
    );
  }

  // Main content
  const content = (
    <div className="space-y-6">
        {(Object.keys(ADMIN_CONNECTOR_CATEGORIES) as CategoryKey[]).map(categoryKey => {
          const connectors = ADMIN_CONNECTOR_CATEGORIES[categoryKey];

          return (
            <div key={categoryKey}>
              <div className="mb-3">
                <h3 className="text-lg font-medium text-foreground">
                  {t(`settings.admin.connectors.categories.${categoryKey}.label`)}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {t(`settings.admin.connectors.categories.${categoryKey}.description`)}
                </p>
              </div>
              <div className="space-y-2">
                {connectors.map(connectorType => {
                  const config = getConfig(connectorType);
                  const enabled = isEnabled(connectorType);

                  return (
                    <div
                      key={connectorType}
                      className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">
                            {getConnectorLabel(connectorType)}
                          </span>
                          {enabled ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300">
                              {t('settings.admin.connectors.status.enabled')}
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300">
                              {t('settings.admin.connectors.status.disabled')}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                          {t(`settings.admin.connectors.connector_descriptions.${connectorType}`)}
                        </div>
                        {config?.disabled_reason && (
                          <div className="text-xs text-destructive mt-1">
                            {t('settings.admin.connectors.reason_label')} {config.disabled_reason}
                          </div>
                        )}
                      </div>
                      <Button
                        variant={enabled ? 'destructive' : 'success'}
                        size="sm"
                        onClick={() => handleToggle(connectorType, enabled)}
                        className="min-w-[100px] justify-center"
                      >
                        {enabled ? t('settings.admin.connectors.actions.disable') : t('settings.admin.connectors.actions.enable')}
                      </Button>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
    </div>
  );

  return (
    <SettingsSection
      value="admin-connectors"
      title={t('settings.admin.connectors.title')}
      description={t('settings.admin.connectors.description')}
      icon={Plug}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
