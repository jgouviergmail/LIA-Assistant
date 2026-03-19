'use client';

import { toast } from 'sonner';
import { Bug } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';

import type { BaseSettingsProps } from '@/types/settings';

// API endpoint constants
const DEBUG_PANEL_ENDPOINT = '/admin/system-settings/debug-panel';
const DEBUG_PANEL_USER_ACCESS_ENDPOINT = '/admin/system-settings/debug-panel-user-access';

interface DebugPanelEnabledResponse {
  enabled: boolean;
  updated_by: string | null;
  updated_at: string | null;
  is_default: boolean;
}

interface DebugPanelUserAccessResponse {
  available: boolean;
  updated_by: string | null;
  updated_at: string | null;
  is_default: boolean;
}

export default function AdminDebugSettingsSection({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');

  // Fetch current debug panel status (admin's own debug panel)
  const {
    data: debugPanel,
    loading: loadingPanel,
    setData: setDebugPanel,
  } = useApiQuery<DebugPanelEnabledResponse>(DEBUG_PANEL_ENDPOINT, {
    componentName: 'AdminDebugSettingsSection',
    initialData: {
      enabled: false,
      updated_by: null,
      updated_at: null,
      is_default: true,
    },
  });

  // Fetch current user access status
  const {
    data: userAccess,
    loading: loadingUserAccess,
    setData: setUserAccess,
  } = useApiQuery<DebugPanelUserAccessResponse>(DEBUG_PANEL_USER_ACCESS_ENDPOINT, {
    componentName: 'AdminDebugSettingsSection.userAccess',
    initialData: {
      available: false,
      updated_by: null,
      updated_at: null,
      is_default: true,
    },
  });

  // Mutation for updating debug panel status
  const { mutate: updateStatus, loading: updatingPanel } = useApiMutation({
    method: 'PUT',
    componentName: 'AdminDebugSettingsSection',
  });

  // Mutation for updating user access status
  const { mutate: updateUserAccess, loading: updatingUserAccess } = useApiMutation({
    method: 'PUT',
    componentName: 'AdminDebugSettingsSection.userAccess',
  });

  const loading = loadingPanel || loadingUserAccess;
  const isEnabled = debugPanel?.enabled ?? false;
  const isUserAccessEnabled = userAccess?.available ?? false;

  const handleTogglePanel = async (checked: boolean) => {
    try {
      await updateStatus(DEBUG_PANEL_ENDPOINT, { enabled: checked });

      // Optimistic update
      setDebugPanel(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          enabled: checked,
          is_default: false,
          updated_at: new Date().toISOString(),
        };
      });

      toast.success(
        checked
          ? t('settings.admin.debug.enabledSuccess')
          : t('settings.admin.debug.disabledSuccess')
      );
    } catch {
      toast.error(t('settings.admin.debug.error'));
    }
  };

  const handleToggleUserAccess = async (checked: boolean) => {
    try {
      await updateUserAccess(DEBUG_PANEL_USER_ACCESS_ENDPOINT, { available: checked });

      // Optimistic update
      setUserAccess(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          available: checked,
          is_default: false,
          updated_at: new Date().toISOString(),
        };
      });

      toast.success(
        checked
          ? t('settings.admin.debug.userAccessEnabledSuccess')
          : t('settings.admin.debug.userAccessDisabledSuccess')
      );
    } catch {
      toast.error(t('settings.admin.debug.error'));
    }
  };

  const content = loading ? (
    <div className="animate-pulse text-muted-foreground py-4">{t('common.loading')}</div>
  ) : (
    <div className="space-y-6">
      {/* Debug Panel Toggle (Admin's own) */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between p-4 border border-border rounded-lg">
        <div className="flex-1 space-y-1">
          <Label htmlFor="debug-panel" className="text-base font-medium">
            {t('settings.admin.debug.panelLabel')}
          </Label>
          <div className="text-sm text-muted-foreground">
            {isEnabled ? (
              <span className="text-green-600 dark:text-green-400 font-medium">
                {t('settings.admin.debug.statusEnabled')}
              </span>
            ) : (
              <span className="text-muted-foreground">
                {t('settings.admin.debug.statusDisabled')}
              </span>
            )}
          </div>
          {debugPanel?.updated_at && !debugPanel?.is_default && (
            <div className="text-xs text-muted-foreground mt-1">
              {t('settings.admin.debug.lastUpdated')}:{' '}
              {new Date(debugPanel.updated_at).toLocaleString(lng)}
            </div>
          )}
          {debugPanel?.is_default && (
            <div className="text-xs text-muted-foreground mt-1">
              {t('settings.admin.debug.usingDefault')}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-sm text-muted-foreground">{t('common.off')}</span>
          <Switch
            id="debug-panel"
            checked={isEnabled}
            onCheckedChange={handleTogglePanel}
            disabled={updatingPanel}
            aria-label={t('settings.admin.debug.toggleLabel')}
          />
          <span className="text-sm font-medium text-primary">{t('common.on')}</span>
        </div>
      </div>

      {/* User Access Toggle */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between p-4 border border-border rounded-lg">
        <div className="flex-1 space-y-1">
          <Label htmlFor="debug-panel-user-access" className="text-base font-medium">
            {t('settings.admin.debug.userAccessLabel')}
          </Label>
          <div className="text-sm text-muted-foreground">
            {isUserAccessEnabled ? (
              <span className="text-green-600 dark:text-green-400 font-medium">
                {t('settings.admin.debug.userAccessStatusEnabled')}
              </span>
            ) : (
              <span className="text-muted-foreground">
                {t('settings.admin.debug.userAccessStatusDisabled')}
              </span>
            )}
          </div>
          {userAccess?.updated_at && !userAccess?.is_default && (
            <div className="text-xs text-muted-foreground mt-1">
              {t('settings.admin.debug.lastUpdated')}:{' '}
              {new Date(userAccess.updated_at).toLocaleString(lng)}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-sm text-muted-foreground">{t('common.off')}</span>
          <Switch
            id="debug-panel-user-access"
            checked={isUserAccessEnabled}
            onCheckedChange={handleToggleUserAccess}
            disabled={updatingUserAccess}
            aria-label={t('settings.admin.debug.userAccessToggleLabel')}
          />
          <span className="text-sm font-medium text-primary">{t('common.on')}</span>
        </div>
      </div>

      {/* Info Box */}
      <InfoBox className="p-4">
        <div className="text-sm text-muted-foreground space-y-2">
          <p>
            <strong className="text-foreground">{t('settings.admin.debug.whatItDoes')}:</strong>{' '}
            {t('settings.admin.debug.description')}
          </p>
          <p className="text-xs">{t('settings.admin.debug.note')}</p>
        </div>
      </InfoBox>
    </div>
  );

  return (
    <SettingsSection
      value="debug-settings"
      icon={Bug}
      title={t('settings.admin.debug.title')}
      description={t('settings.admin.debug.subtitle')}
      collapsible={collapsible}
    >
      {content}
    </SettingsSection>
  );
}
