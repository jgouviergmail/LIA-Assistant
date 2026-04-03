'use client';

import React from 'react';
import { APP_VERSION } from '@/lib/version';
import { useAuth } from '@/hooks/useAuth';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Accordion } from '@/components/ui/accordion';
import {
  Settings,
  Shield,
  Puzzle,
  Palette,
  Bell,
  Mic,
  Plug,
  Brain,
  Zap,
  Blocks,
  Users,
  Cpu,
  Sparkles,
  Wrench,
} from 'lucide-react';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import UserConnectorsSection from '@/components/settings/UserConnectorsSection';
import AdminUsersSection from '@/components/settings/AdminUsersSection';
import AdminConnectorsSection from '@/components/settings/AdminConnectorsSection';
import AdminLLMPricingSection from '@/components/settings/AdminLLMPricingSection';
import AdminGoogleApiPricingSection from '@/components/settings/AdminGoogleApiPricingSection';
import AdminImagePricingSection from '@/components/settings/AdminImagePricingSection';
import AdminPersonalitiesSection from '@/components/settings/AdminPersonalitiesSection';
import AdminVoiceSettingsSection from '@/components/settings/AdminVoiceSettingsSection';
import AdminBroadcastSection from '@/components/settings/AdminBroadcastSection';
import AdminConsumptionExportSection from '@/components/settings/AdminConsumptionExportSection';
import AdminDebugSettingsSection from '@/components/settings/AdminDebugSettingsSection';
import AdminLLMConfigSection from '@/components/settings/AdminLLMConfigSection';
import AdminRAGSpacesSection from '@/components/settings/AdminRAGSpacesSection';
import { ThemeSelector } from '@/components/theme-selector';
import { FontSettings } from '@/components/settings/FontSettings';
import { TimezoneSelector } from '@/components/settings/TimezoneSelector';
import { LanguageSettings } from '@/components/settings/LanguageSettings';
import { PersonalitySettings } from '@/components/settings/PersonalitySettings';
import { MemorySettings } from '@/components/settings/MemorySettings';
import { InterestsSettings } from '@/components/settings/InterestsSettings';
import { NotificationSettings } from '@/components/settings/NotificationSettings';
import { ScheduledActionsSettings } from '@/components/settings/ScheduledActionsSettings';
import { AdminMCPServersSettings } from '@/components/settings/AdminMCPServersSettings';
import { MCPServersSettings } from '@/components/settings/MCPServersSettings';
import { ChannelSettings } from '@/components/settings/ChannelSettings';
import { HeartbeatSettings } from '@/components/settings/HeartbeatSettings';
import { JournalsSettings } from '@/components/settings/JournalsSettings';
import { PsycheSettings } from '@/components/settings/PsycheSettings';
import { SkillsSettings } from '@/components/settings/SkillsSettings';
import { AdminSkillsSection } from '@/components/settings/AdminSkillsSection';
import { AdminUsageLimitsSection } from '@/components/settings/AdminUsageLimitsSection';
import { SpacesSettingsSection } from '@/components/spaces/SpacesSettingsSection';
import { VoiceModeSettings } from '@/components/settings/VoiceModeSettings';
import { ImageGenerationSettings } from '@/components/settings/ImageGenerationSettings';
import { UserDebugSettings } from '@/components/settings/UserDebugSettings';
import { CardsDisplaySettings } from '@/components/settings/CardsDisplaySettings';
import { SettingsGroupLabel } from '@/components/settings/SettingsGroupLabel';
import ConsumptionExportSection from '@/components/settings/ConsumptionExportSection';
import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useTranslation } from '@/i18n/client';
import { FeatureErrorBoundary } from '@/components/errors';

interface SettingsPageProps {
  params: Promise<{ lng: string }>;
}

export default function SettingsPage({ params }: SettingsPageProps) {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const { userAccessAvailable } = useDebugPanelEnabled();

  // Track expanded sections for each accordion (by tab for superusers)
  const [appearanceSections, setAppearanceSections] = React.useState<string[]>([]);
  const [featuresSections, setFeaturesSections] = React.useState<string[]>([]);
  const [connectorSections, setConnectorSections] = React.useState<string[]>([]);
  // For non-superusers: single accordion with all sections
  const [allSections, setAllSections] = React.useState<string[]>([]);

  // Track active tab for superusers
  const [activeTab, setActiveTab] = React.useState('preferences');

  // Track if we should auto-expand connectors section after OAuth callback
  const [shouldExpandConnectors, setShouldExpandConnectors] = React.useState(false);

  // Track if OAuth callback toast has been shown (prevents duplicate toasts)
  const oauthToastShownRef = React.useRef(false);

  React.useEffect(() => {
    const connectorAdded = searchParams.get('connector_added');
    const connectorType = searchParams.get('connector_type');
    const error = searchParams.get('error');
    const section = searchParams.get('section');

    // Handle direct navigation to a section (e.g., from dashboard)
    if (section === 'connectors') {
      setShouldExpandConnectors(true);
      // Clean URL param
      const url = new URL(window.location.href);
      url.searchParams.delete('section');
      window.history.replaceState({}, '', url.toString());
    }

    if (connectorAdded === 'true' && connectorType && !oauthToastShownRef.current) {
      // Mark toast as shown to prevent duplicates
      oauthToastShownRef.current = true;

      // Get connector display name from centralized constants
      // Handle legacy google_gmail -> gmail mapping
      const normalizedType = connectorType === 'google_gmail' ? 'gmail' : connectorType;
      const displayName = isValidConnectorType(normalizedType)
        ? CONNECTOR_LABELS[normalizedType]
        : t('settings.connectors.unknown_connector');
      toast.success(t('settings.connectors.connected_success', { name: displayName }));

      // Clean URL params without page reload
      const url = new URL(window.location.href);
      url.searchParams.delete('connector_added');
      url.searchParams.delete('connector_type');
      url.searchParams.delete('connector_id');
      window.history.replaceState({}, '', url.toString());

      // Auto-expand connectors section (no page reload needed - component will refetch)
      setShouldExpandConnectors(true);
    } else if (error && !oauthToastShownRef.current) {
      // Mark toast as shown to prevent duplicates
      oauthToastShownRef.current = true;

      // Get error message from i18n with fallback to default
      const errorKey = ['invalid_state', 'code_exchange_failed', 'connector_disabled'].includes(
        error
      )
        ? error
        : 'default';
      toast.error(t(`settings.connectors.oauth_errors.${errorKey}`));

      // Clean error param
      const url = new URL(window.location.href);
      url.searchParams.delete('error');
      window.history.replaceState({}, '', url.toString());
    }

    // Handle MCP OAuth callback (evolution F2.1)
    const mcpOAuth = searchParams.get('mcp_oauth');
    if (mcpOAuth && !oauthToastShownRef.current) {
      oauthToastShownRef.current = true;
      if (mcpOAuth === 'success') {
        toast.success(t('settings.mcp.oauth_success'));
      } else {
        toast.error(t('settings.mcp.oauth_error'));
      }
      // Clean URL params
      const url = new URL(window.location.href);
      url.searchParams.delete('mcp_oauth');
      url.searchParams.delete('server_id');
      url.searchParams.delete('error');
      window.history.replaceState({}, '', url.toString());
    }
  }, [searchParams, t]);

  // Auto-expand connectors section when needed
  React.useEffect(() => {
    if (shouldExpandConnectors) {
      // For superusers: switch to preferences tab and expand connectors section
      if (user?.is_superuser) {
        setActiveTab('preferences');
        setAppearanceSections((prev: string[]) =>
          prev.includes('connectors') ? prev : [...prev, 'connectors']
        );
      } else {
        // For non-superusers: expand in the main accordion
        setAllSections((prev: string[]) =>
          prev.includes('connectors') ? prev : [...prev, 'connectors']
        );
      }
      setShouldExpandConnectors(false);
    }
  }, [shouldExpandConnectors, user?.is_superuser]);

  if (!user) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('settings.title')}</h1>
        <p className="mt-2 text-muted-foreground">{t('settings.subtitle')}</p>
      </div>

      {/* Tabs Navigation */}
      {user.is_superuser ? (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="preferences" className="gap-2">
              <Settings className="h-4 w-4" />
              <span>{t('settings.tabs.preferences')}</span>
            </TabsTrigger>
            <TabsTrigger value="features" className="gap-2">
              <Puzzle className="h-4 w-4" />
              <span>{t('settings.tabs.features')}</span>
            </TabsTrigger>
            <TabsTrigger value="administration" className="gap-2">
              <Shield className="h-4 w-4" />
              <span>{t('settings.tabs.administration')}</span>
            </TabsTrigger>
          </TabsList>

          {/* PREFERENCES Tab */}
          <TabsContent value="preferences">
            <Accordion
              type="multiple"
              value={appearanceSections}
              onValueChange={setAppearanceSections}
              className="space-y-4"
            >
              {/* Group: Personalization */}
              <SettingsGroupLabel label={t('settings.groups.personalization')} icon={Palette} />
              <LanguageSettings lng={lng} />
              <TimezoneSelector lng={lng} />
              <ThemeSelector lng={lng} />
              <FontSettings lng={lng} />
              <CardsDisplaySettings lng={lng} />

              {/* Group: Notifications & Communication */}
              <SettingsGroupLabel
                label={t('settings.groups.notifications_communication')}
                icon={Bell}
              />
              <NotificationSettings lng={lng} />
              <FeatureErrorBoundary feature="channels">
                <ChannelSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Voice & Media */}
              <SettingsGroupLabel label={t('settings.groups.voice_media')} icon={Mic} />
              <VoiceModeSettings lng={lng} />
              <FeatureErrorBoundary feature="image-generation">
                <ImageGenerationSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Connections & Integrations */}
              <SettingsGroupLabel
                label={t('settings.groups.connections_integrations')}
                icon={Plug}
              />
              <FeatureErrorBoundary feature="connectors">
                <UserConnectorsSection lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="admin-mcp-servers">
                <AdminMCPServersSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="mcp-servers">
                <MCPServersSettings lng={lng} />
              </FeatureErrorBoundary>
            </Accordion>
          </TabsContent>

          {/* FEATURES Tab */}
          <TabsContent value="features">
            <Accordion
              type="multiple"
              value={featuresSections}
              onValueChange={setFeaturesSections}
              className="space-y-4"
            >
              {/* Group: Identity & Memory */}
              <SettingsGroupLabel label={t('settings.groups.identity_memory')} icon={Brain} />
              <PersonalitySettings lng={lng} />
              <FeatureErrorBoundary feature="psyche">
                <PsycheSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="memory-settings">
                <MemorySettings lng={lng} />
              </FeatureErrorBoundary>
              <InterestsSettings lng={lng} />

              {/* Group: Automation & Tracking */}
              <SettingsGroupLabel label={t('settings.groups.automation_tracking')} icon={Zap} />
              <FeatureErrorBoundary feature="heartbeat">
                <HeartbeatSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="scheduled-actions">
                <ScheduledActionsSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="journals">
                <JournalsSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Extensions & Data */}
              <SettingsGroupLabel label={t('settings.groups.extensions_data')} icon={Blocks} />
              <FeatureErrorBoundary feature="skills">
                <SkillsSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="rag-spaces">
                <SpacesSettingsSection lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="user-consumption-export">
                <ConsumptionExportSection lng={lng} mode="user" />
              </FeatureErrorBoundary>
            </Accordion>
          </TabsContent>

          {/* ADMINISTRATION Tab */}
          <TabsContent value="administration">
            <Accordion
              type="multiple"
              value={connectorSections}
              onValueChange={setConnectorSections}
              className="space-y-4"
            >
              {/* Group: Users & Access */}
              <SettingsGroupLabel label={t('settings.groups.users_access')} icon={Users} />
              <AdminUsersSection lng={lng} />
              <FeatureErrorBoundary feature="usage-limits">
                <AdminUsageLimitsSection lng={lng} />
              </FeatureErrorBoundary>
              <AdminConsumptionExportSection lng={lng} />
              <AdminBroadcastSection lng={lng} />

              {/* Group: AI & Connectors */}
              <SettingsGroupLabel label={t('settings.groups.ai_connectors')} icon={Cpu} />
              <AdminConnectorsSection lng={lng} />
              <AdminLLMPricingSection lng={lng} />
              <AdminGoogleApiPricingSection lng={lng} />
              <AdminImagePricingSection lng={lng} />
              <FeatureErrorBoundary feature="llm-config">
                <AdminLLMConfigSection lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Content & Extensions */}
              <SettingsGroupLabel label={t('settings.groups.content_extensions')} icon={Sparkles} />
              <AdminPersonalitiesSection lng={lng} />
              <FeatureErrorBoundary feature="admin-skills">
                <AdminSkillsSection lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="rag-spaces-admin">
                <AdminRAGSpacesSection lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: System */}
              <SettingsGroupLabel label={t('settings.groups.system')} icon={Wrench} />
              <AdminVoiceSettingsSection lng={lng} />
              <AdminDebugSettingsSection lng={lng} />
            </Accordion>
          </TabsContent>
        </Tabs>
      ) : (
        /* NON-ADMIN: Two-tab layout (Preferences + Features) */
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="preferences" className="gap-2">
              <Settings className="h-4 w-4" />
              <span>{t('settings.tabs.preferences')}</span>
            </TabsTrigger>
            <TabsTrigger value="features" className="gap-2">
              <Puzzle className="h-4 w-4" />
              <span>{t('settings.tabs.features')}</span>
            </TabsTrigger>
          </TabsList>

          {/* PREFERENCES Tab */}
          <TabsContent value="preferences">
            <Accordion
              type="multiple"
              value={allSections}
              onValueChange={setAllSections}
              className="space-y-4"
            >
              {/* Group: Personalization */}
              <SettingsGroupLabel label={t('settings.groups.personalization')} icon={Palette} />
              <LanguageSettings lng={lng} />
              <TimezoneSelector lng={lng} />
              <ThemeSelector lng={lng} />
              <FontSettings lng={lng} />
              <CardsDisplaySettings lng={lng} />

              {/* Group: Notifications & Communication */}
              <SettingsGroupLabel
                label={t('settings.groups.notifications_communication')}
                icon={Bell}
              />
              <NotificationSettings lng={lng} />
              <FeatureErrorBoundary feature="channels">
                <ChannelSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Voice & Media */}
              <SettingsGroupLabel label={t('settings.groups.voice_media')} icon={Mic} />
              <VoiceModeSettings lng={lng} />
              <FeatureErrorBoundary feature="image-generation">
                <ImageGenerationSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Connections & Integrations */}
              <SettingsGroupLabel
                label={t('settings.groups.connections_integrations')}
                icon={Plug}
              />
              <FeatureErrorBoundary feature="connectors">
                <UserConnectorsSection lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="admin-mcp-servers">
                <AdminMCPServersSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="mcp-servers">
                <MCPServersSettings lng={lng} />
              </FeatureErrorBoundary>
              {userAccessAvailable && <UserDebugSettings lng={lng} />}
            </Accordion>
          </TabsContent>

          {/* FEATURES Tab */}
          <TabsContent value="features">
            <Accordion
              type="multiple"
              value={featuresSections}
              onValueChange={setFeaturesSections}
              className="space-y-4"
            >
              {/* Group: Identity & Memory */}
              <SettingsGroupLabel label={t('settings.groups.identity_memory')} icon={Brain} />
              <PersonalitySettings lng={lng} />
              <FeatureErrorBoundary feature="psyche">
                <PsycheSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="memory-settings">
                <MemorySettings lng={lng} />
              </FeatureErrorBoundary>
              <InterestsSettings lng={lng} />

              {/* Group: Automation & Tracking */}
              <SettingsGroupLabel label={t('settings.groups.automation_tracking')} icon={Zap} />
              <FeatureErrorBoundary feature="heartbeat">
                <HeartbeatSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="scheduled-actions">
                <ScheduledActionsSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="journals">
                <JournalsSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Extensions & Data */}
              <SettingsGroupLabel label={t('settings.groups.extensions_data')} icon={Blocks} />
              <FeatureErrorBoundary feature="skills">
                <SkillsSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="rag-spaces">
                <SpacesSettingsSection lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="user-consumption-export">
                <ConsumptionExportSection lng={lng} mode="user" />
              </FeatureErrorBoundary>
            </Accordion>
          </TabsContent>
        </Tabs>
      )}

      {/* Version */}
      <p className="text-xs text-muted-foreground/50 text-center pt-4">v{APP_VERSION}</p>
    </div>
  );
}
