'use client';

import React from 'react';
import { APP_VERSION } from '@/lib/version';
import { useAuth } from '@/hooks/useAuth';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import { Tabs, TabsContent } from '@/components/ui/tabs';
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
import TelephonyCallsSection from '@/components/settings/TelephonyCallsSection';
import AdminUsersSection from '@/components/settings/AdminUsersSection';
import AdminConnectorsSection from '@/components/settings/AdminConnectorsSection';
import AdminLLMPricingSection from '@/components/settings/AdminLLMPricingSection';
import AdminGoogleApiPricingSection from '@/components/settings/AdminGoogleApiPricingSection';
import AdminImagePricingSection from '@/components/settings/AdminImagePricingSection';
import AdminPersonalitiesSection from '@/components/settings/AdminPersonalitiesSection';
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
import { PortraitShortcut } from '@/components/settings/PortraitShortcut';
import { HealthMetricsSettings } from '@/components/settings/HealthMetricsSettings';
import { PsycheSettings } from '@/components/settings/PsycheSettings';
import { SkillsSettings } from '@/components/settings/SkillsSettings';
import { AdminSkillsSection } from '@/components/settings/AdminSkillsSection';
import { AdminUsageLimitsSection } from '@/components/settings/AdminUsageLimitsSection';
import { SpacesSettingsSection } from '@/components/spaces/SpacesSettingsSection';
import { VoiceModeSettings } from '@/components/settings/VoiceModeSettings';
import { ImageGenerationSettings } from '@/components/settings/ImageGenerationSettings';
import { UserDebugSettings } from '@/components/settings/UserDebugSettings';
import { BriefingGridSettings } from '@/components/settings/BriefingGridSettings';
import { OpenLoopsSection } from '@/components/settings/OpenLoopsSection';
import { CardsDisplaySettings } from '@/components/settings/CardsDisplaySettings';
import { SettingsGroupLabel } from '@/components/settings/SettingsGroupLabel';
import { SettingsTabsBar } from '@/components/settings/SettingsTabsBar';
import { SecuritySettings } from '@/components/settings/SecuritySettings';
import { DeviceSessionsSettings } from '@/components/settings/DeviceSessionsSettings';
import { AccountExportSettings } from '@/components/settings/AccountExportSettings';
import ConsumptionExportSection from '@/components/settings/ConsumptionExportSection';
import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useTranslation } from '@/i18n/client';
import { FeatureErrorBoundary } from '@/components/errors';
import { CatalogueInvalidationProvider } from '@/lib/catalogue-invalidation-context';
import {
  SETTINGS_SECTIONS,
  resolveSettingsSection,
  type SettingsSectionTarget,
} from '@/lib/settings-sections';

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

  // W2: pending `?section=` target. Any token of SETTINGS_SECTIONS opens its
  // tab, expands its accordion item and scrolls to it — previously only
  // `connectors` and `journals` were understood, while the getting-started
  // checklist pointed six of its seven items at the bare settings page.
  const [pendingSection, setPendingSection] = React.useState<SettingsSectionTarget | null>(null);

  // Track if OAuth callback toast has been shown (prevents duplicate toasts)
  const oauthToastShownRef = React.useRef(false);

  React.useEffect(() => {
    const connectorAdded = searchParams.get('connector_added');
    const connectorType = searchParams.get('connector_type');
    const error = searchParams.get('error');
    const section = searchParams.get('section');

    // Handle direct navigation to a section (from the dashboard, the starter
    // checklist, a briefing card…). The token maps to a tab + accordion target
    // through SETTINGS_SECTIONS; an unknown token simply resolves to null and
    // leaves the page on its default tab. The param is cleaned either way so a
    // reload does not replay the navigation.
    const target = resolveSettingsSection(section);
    if (target) {
      setPendingSection(target);
    }
    if (section) {
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

  // The OAuth callback lands on the connectors section — same mechanism as a
  // `?section=` deep link, so it goes through the same state.
  React.useEffect(() => {
    if (!shouldExpandConnectors) return;
    setPendingSection(SETTINGS_SECTIONS.connectors);
    setShouldExpandConnectors(false);
  }, [shouldExpandConnectors]);

  // W2: honour a pending section target — activate its tab, expand its
  // accordion item, scroll to it. Which accordion holds it depends on the tab
  // AND on the layout: superusers get three tabs (preferences / features /
  // administration), everyone else two, and the non-superuser preferences tab
  // uses its own `allSections` state.
  React.useEffect(() => {
    if (!pendingSection) return;
    const { tab, accordionValue } = pendingSection;
    setActiveTab(tab);

    const expand = (prev: string[]) =>
      prev.includes(accordionValue) ? prev : [...prev, accordionValue];
    if (tab === 'features') {
      setFeaturesSections(expand);
    } else if (tab === 'administration') {
      setConnectorSections(expand);
    } else if (user?.is_superuser) {
      setAppearanceSections(expand);
    } else {
      setAllSections(expand);
    }

    // The accordion animates open; scrolling before it has height would land
    // short. The id is derived from the same `value` (SettingsSection).
    const timer = window.setTimeout(() => {
      document
        .getElementById(`settings-section-${accordionValue}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setPendingSection(null);
    }, 150);
    return () => window.clearTimeout(timer);
  }, [pendingSection, user?.is_superuser]);

  if (!user) return null;

  // The tab bar is sticky, so a tab can now be switched from anywhere down the
  // page — which would otherwise drop the reader into the MIDDLE of the new
  // tab's content. Land them at the top of it instead. Instant, not smooth:
  // `behavior: 'smooth'` in JS ignores `prefers-reduced-motion`.
  const handleTabChange = (value: string) => {
    setActiveTab(value);
    window.scrollTo({ top: 0 });
  };

  // Declared once, consumed by both layouts (superusers get the third tab).
  const preferencesTab = {
    value: 'preferences',
    label: t('settings.tabs.preferences'),
    icon: Settings,
  };
  const featuresTab = { value: 'features', label: t('settings.tabs.features'), icon: Puzzle };
  const administrationTab = {
    value: 'administration',
    label: t('settings.tabs.administration'),
    icon: Shield,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('settings.title')}</h1>
        <p className="mt-2 text-muted-foreground">{t('settings.subtitle')}</p>
      </div>

      {/* Tabs Navigation */}
      {user.is_superuser ? (
        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
          <SettingsTabsBar tabs={[preferencesTab, featuresTab, administrationTab]} />

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
              <BriefingGridSettings lng={lng} />
              <OpenLoopsSection lng={lng} />

              {/* Group: Notifications & Communication */}
              <SettingsGroupLabel
                label={t('settings.groups.notifications_communication')}
                icon={Bell}
              />
              <NotificationSettings lng={lng} />
              <FeatureErrorBoundary feature="channels">
                <ChannelSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Security — device sessions always; passkeys/TOTP/password
                  render only when the instance has MFA enabled */}
              <SettingsGroupLabel label={t('settings.groups.security')} icon={Shield} />
              <FeatureErrorBoundary feature="security">
                <SecuritySettings />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="security">
                <DeviceSessionsSettings />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="security">
                <AccountExportSettings />
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
              {/* A6: the calls surface the backend already served, and
                  nothing consumed. Renders nothing when telephony is off
                  or no call was ever placed. */}
              <FeatureErrorBoundary feature="telephony-calls">
                <TelephonyCallsSection lng={lng} />
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
              {/* QW-10: "What LIA understands about you" — jumps to the
                  portrait inside Journals (renders only with a portrait). */}
              <FeatureErrorBoundary feature="journals">
                <PortraitShortcut onOpen={() => setPendingSection(SETTINGS_SECTIONS.journals)} />
              </FeatureErrorBoundary>
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
              <FeatureErrorBoundary feature="health-metrics">
                <HealthMetricsSettings lng={lng} />
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
              {/* Tarification (Texte/Image) emit catalogue invalidation events
                  that Configuration LLM listens to, so dropdowns refresh
                  immediately after an admin mutation without a page reload. */}
              <CatalogueInvalidationProvider>
                <AdminLLMPricingSection lng={lng} />
                <AdminGoogleApiPricingSection lng={lng} />
                <AdminImagePricingSection lng={lng} />
                <FeatureErrorBoundary feature="llm-config">
                  <AdminLLMConfigSection lng={lng} />
                </FeatureErrorBoundary>
              </CatalogueInvalidationProvider>

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
              <AdminDebugSettingsSection lng={lng} />
            </Accordion>
          </TabsContent>
        </Tabs>
      ) : (
        /* NON-ADMIN: Two-tab layout (Preferences + Features) */
        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
          <SettingsTabsBar tabs={[preferencesTab, featuresTab]} />

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
              <BriefingGridSettings lng={lng} />
              <OpenLoopsSection lng={lng} />

              {/* Group: Notifications & Communication */}
              <SettingsGroupLabel
                label={t('settings.groups.notifications_communication')}
                icon={Bell}
              />
              <NotificationSettings lng={lng} />
              <FeatureErrorBoundary feature="channels">
                <ChannelSettings lng={lng} />
              </FeatureErrorBoundary>

              {/* Group: Security — device sessions always; passkeys/TOTP/password
                  render only when the instance has MFA enabled */}
              <SettingsGroupLabel label={t('settings.groups.security')} icon={Shield} />
              <FeatureErrorBoundary feature="security">
                <SecuritySettings />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="security">
                <DeviceSessionsSettings />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="security">
                <AccountExportSettings />
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
              {/* A6: the calls surface the backend already served, and
                  nothing consumed. Renders nothing when telephony is off
                  or no call was ever placed. */}
              <FeatureErrorBoundary feature="telephony-calls">
                <TelephonyCallsSection lng={lng} />
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
              {/* QW-10: "What LIA understands about you" — jumps to the
                  portrait inside Journals (renders only with a portrait). */}
              <FeatureErrorBoundary feature="journals">
                <PortraitShortcut onOpen={() => setPendingSection(SETTINGS_SECTIONS.journals)} />
              </FeatureErrorBoundary>
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
              <FeatureErrorBoundary feature="health-metrics">
                <HealthMetricsSettings lng={lng} />
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
      <p className="text-xs text-muted-foreground text-center pt-4">v{APP_VERSION}</p>
    </div>
  );
}
