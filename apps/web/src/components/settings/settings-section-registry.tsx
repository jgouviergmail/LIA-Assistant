'use client';

/**
 * Section token → how the master-detail pane renders it.
 *
 * The single place where a token becomes a mounted component. The page used to
 * hand-list every section twice (one layout per superuser flag); the pane now
 * resolves the selected token here, so a section exists on the page if and
 * only if it exists in `SETTINGS_SECTIONS` — the drift class the old
 * source-parsing guards existed to catch is structurally gone.
 *
 * `feature` is the `FeatureErrorBoundary` label the old page wrapped the
 * section with; entries without one render bare, exactly as before. Agreement
 * between each renderer and `declaredIn` is held by
 * `__tests__/settings-section-registry.test.tsx`.
 */

import type { ReactElement } from 'react';

import type { Language } from '@/i18n/settings';
import type { SettingsSectionToken } from '@/lib/settings-sections';

export interface SettingsSectionEntry {
  /** `FeatureErrorBoundary` label; absent = the section renders unwrapped. */
  feature?: string;
  /** The section, exactly as the accordion page used to mount it. */
  render: (lng: Language) => Promise<ReactElement>;
}

export const SETTINGS_SECTION_REGISTRY: Readonly<
  Record<SettingsSectionToken, SettingsSectionEntry>
> = {
  // ---- Preferences / Personalization
  language: {
    render: async lng => {
      const { LanguageSettings } = await import('./LanguageSettings');
      return <LanguageSettings lng={lng} />;
    },
  },
  timezone: {
    render: async lng => {
      const { TimezoneSelector } = await import('./TimezoneSelector');
      return <TimezoneSelector lng={lng} />;
    },
  },
  location: {
    render: async lng => {
      const { LocationSettings } = await import('./LocationSettings');
      return <LocationSettings lng={lng} />;
    },
  },
  theme: {
    render: async lng => {
      const { ThemeSelector } = await import('@/components/theme-selector');
      return <ThemeSelector lng={lng} />;
    },
  },
  font: {
    render: async lng => {
      const { FontSettings } = await import('./FontSettings');
      return <FontSettings lng={lng} />;
    },
  },
  'font-size': {
    render: async lng => {
      const { FontSizeSettings } = await import('./FontSizeSettings');
      return <FontSizeSettings lng={lng} />;
    },
  },
  'eyes-style': {
    render: async lng => {
      const { EyesStyleSettings } = await import('./EyesStyleSettings');
      return <EyesStyleSettings lng={lng} />;
    },
  },
  'display-mode': {
    render: async lng => {
      const { CardsDisplaySettings } = await import('./CardsDisplaySettings');
      return <CardsDisplaySettings lng={lng} />;
    },
  },
  'usage-preferences': {
    render: async lng => {
      const { UsagePreferencesSettings } = await import('./UsagePreferencesSettings');
      return <UsagePreferencesSettings lng={lng} />;
    },
  },
  haptics: {
    render: async lng => {
      const { HapticsSettings } = await import('./HapticsSettings');
      return <HapticsSettings lng={lng} />;
    },
  },
  'briefing-grid': {
    render: async lng => {
      const { BriefingGridSettings } = await import('./BriefingGridSettings');
      return <BriefingGridSettings lng={lng} />;
    },
  },
  'chat-shortcuts': {
    render: async lng => {
      const { ChatShortcutsSettings } = await import('./ChatShortcutsSettings');
      return <ChatShortcutsSettings lng={lng} />;
    },
  },
  'my-shortcuts': {
    render: async lng => {
      const { MyShortcutsSettings } = await import('./MyShortcutsSettings');
      return <MyShortcutsSettings lng={lng} />;
    },
  },

  // ---- Preferences / Notifications & Communication
  notifications: {
    render: async lng => {
      const { NotificationSettings } = await import('./NotificationSettings');
      return <NotificationSettings lng={lng} />;
    },
  },
  channels: {
    feature: 'channels',
    render: async lng => {
      const { ChannelSettings } = await import('./ChannelSettings');
      return <ChannelSettings lng={lng} />;
    },
  },

  // ---- Preferences / Security
  'security-auth': {
    feature: 'security',
    render: async () => {
      const { SecuritySettings } = await import('./SecuritySettings');
      return <SecuritySettings />;
    },
  },
  'security-devices': {
    feature: 'security',
    render: async () => {
      const { DeviceSessionsSettings } = await import('./DeviceSessionsSettings');
      return <DeviceSessionsSettings />;
    },
  },
  'security-export': {
    feature: 'security',
    render: async () => {
      const { AccountExportSettings } = await import('./AccountExportSettings');
      return <AccountExportSettings />;
    },
  },

  // ---- Preferences / Voice & Media
  'voice-mode': {
    render: async lng => {
      const { VoiceModeSettings } = await import('./VoiceModeSettings');
      return <VoiceModeSettings lng={lng} />;
    },
  },
  'live-mode': {
    feature: 'live-mode',
    render: async lng => {
      const { LiveModeSettings } = await import('./LiveModeSettings');
      return <LiveModeSettings lng={lng} />;
    },
  },
  avatar: {
    feature: 'avatar',
    render: async lng => {
      const { AvatarSettings } = await import('./AvatarSettings');
      return <AvatarSettings lng={lng} />;
    },
  },
  radio: {
    feature: 'radio',
    render: async lng => {
      const { RadioSettings } = await import('@/components/radio/settings/RadioSettings');
      return <RadioSettings lng={lng} />;
    },
  },
  'image-generation': {
    feature: 'image-generation',
    render: async lng => {
      const { ImageGenerationSettings } = await import('./ImageGenerationSettings');
      return <ImageGenerationSettings lng={lng} />;
    },
  },
  'generated-assets': {
    feature: 'generated-assets',
    render: async lng => {
      const { GeneratedAssetsSettings } = await import('./GeneratedAssetsSettings');
      return <GeneratedAssetsSettings lng={lng} />;
    },
  },

  // ---- Preferences / Connections & Integrations
  connectors: {
    feature: 'connectors',
    render: async lng => {
      const { default: UserConnectorsSection } = await import('./UserConnectorsSection');
      return <UserConnectorsSection lng={lng} />;
    },
  },
  'telephony-calls': {
    feature: 'telephony-calls',
    render: async lng => {
      const { default: TelephonyCallsSection } = await import('./TelephonyCallsSection');
      return <TelephonyCallsSection lng={lng} />;
    },
  },
  'telephony-identity': {
    feature: 'telephony-identity',
    render: async lng => {
      const { default: TelephonyIdentitySection } = await import('./TelephonyIdentitySection');
      return <TelephonyIdentitySection lng={lng} />;
    },
  },
  'admin-mcp-servers': {
    feature: 'admin-mcp-servers',
    render: async lng => {
      const { AdminMCPServersSettings } = await import('./AdminMCPServersSettings');
      return <AdminMCPServersSettings lng={lng} />;
    },
  },
  'mcp-servers': {
    feature: 'mcp-servers',
    render: async lng => {
      const { MCPServersSettings } = await import('./MCPServersSettings');
      return <MCPServersSettings lng={lng} />;
    },
  },
  'sandbox-egress': {
    feature: 'sandbox-egress',
    render: async lng => {
      const { SandboxEgressSettings } = await import('./SandboxEgressSettings');
      return <SandboxEgressSettings lng={lng} />;
    },
  },
  'debug-panel': {
    render: async lng => {
      const { UserDebugSettings } = await import('./UserDebugSettings');
      return <UserDebugSettings lng={lng} />;
    },
  },

  // ---- Features / Identity & Memory
  personality: {
    render: async lng => {
      const { PersonalitySettings } = await import('./PersonalitySettings');
      return <PersonalitySettings lng={lng} />;
    },
  },
  psyche: {
    feature: 'psyche',
    render: async lng => {
      const { PsycheSettings } = await import('./PsycheSettings');
      return <PsycheSettings lng={lng} />;
    },
  },
  memories: {
    feature: 'memory-settings',
    render: async lng => {
      const { MemorySettings } = await import('./MemorySettings');
      return <MemorySettings lng={lng} />;
    },
  },
  interests: {
    render: async lng => {
      const { InterestsSettings } = await import('./InterestsSettings');
      return <InterestsSettings lng={lng} />;
    },
  },
  'open-loops': {
    render: async lng => {
      const { OpenLoopsSection } = await import('./OpenLoopsSection');
      return <OpenLoopsSection lng={lng} />;
    },
  },
  habits: {
    feature: 'habits',
    render: async lng => {
      const { HabitsSettings } = await import('./HabitsSettings');
      return <HabitsSettings lng={lng} />;
    },
  },
  'peer-connections': {
    feature: 'peer-connections',
    render: async lng => {
      const { PeerConnectionsSettings } = await import('./PeerConnectionsSettings');
      return <PeerConnectionsSettings lng={lng} />;
    },
  },

  // ---- Features / Automation & Tracking
  heartbeat: {
    feature: 'heartbeat',
    render: async lng => {
      const { HeartbeatSettings } = await import('./HeartbeatSettings');
      return <HeartbeatSettings lng={lng} />;
    },
  },
  'proactive-discussions': {
    render: async lng => {
      const { ProactiveDiscussionSettings } = await import('./ProactiveDiscussionSettings');
      return <ProactiveDiscussionSettings lng={lng} />;
    },
  },
  'scheduled-actions': {
    feature: 'scheduled-actions',
    render: async lng => {
      const { ScheduledActionsSettings } = await import('./ScheduledActionsSettings');
      return <ScheduledActionsSettings lng={lng} />;
    },
  },
  reminders: {
    feature: 'reminders',
    render: async lng => {
      const { RemindersSettings } = await import('./RemindersSettings');
      return <RemindersSettings lng={lng} />;
    },
  },
  journals: {
    feature: 'journals',
    render: async lng => {
      const { JournalsSettings } = await import('./JournalsSettings');
      return <JournalsSettings lng={lng} />;
    },
  },
  'health-metrics': {
    feature: 'health-metrics',
    render: async lng => {
      const { HealthMetricsSettings } = await import('./HealthMetricsSettings');
      return <HealthMetricsSettings lng={lng} />;
    },
  },

  // ---- Features / Extensions & Data
  skills: {
    feature: 'skills',
    render: async lng => {
      const { SkillsSettings } = await import('./SkillsSettings');
      return <SkillsSettings lng={lng} />;
    },
  },
  plugins: {
    feature: 'plugins',
    render: async lng => {
      const { PluginsSettings } = await import('./PluginsSettings');
      return <PluginsSettings lng={lng} />;
    },
  },
  'rag-spaces': {
    feature: 'rag-spaces',
    render: async lng => {
      const { SpacesSettingsSection } = await import('@/components/spaces/SpacesSettingsSection');
      return <SpacesSettingsSection lng={lng} />;
    },
  },
  meetings: {
    feature: 'meetings',
    render: async lng => {
      const { MeetingsSettings } = await import('./MeetingsSettings');
      return <MeetingsSettings lng={lng} />;
    },
  },
  sms: {
    feature: 'sms',
    render: async lng => {
      const { SmsSettings } = await import('./SmsSettings');
      return <SmsSettings lng={lng} />;
    },
  },
  workboard: {
    feature: 'workboard',
    render: async lng => {
      const { WorkboardSettings } = await import('@/components/settings/WorkboardSettings');
      return <WorkboardSettings lng={lng} />;
    },
  },
  'user-consumption-export': {
    feature: 'user-consumption-export',
    render: async lng => {
      const { default: ConsumptionExportSection } = await import('./ConsumptionExportSection');
      return <ConsumptionExportSection lng={lng} mode="user" />;
    },
  },

  // ---- Administration / Users & Access
  'admin-users': {
    render: async lng => {
      const { default: AdminUsersSection } = await import('./AdminUsersSection');
      return <AdminUsersSection lng={lng} />;
    },
  },
  'admin-usage-limits': {
    feature: 'usage-limits',
    render: async lng => {
      const { AdminUsageLimitsSection } = await import('./AdminUsageLimitsSection');
      return <AdminUsageLimitsSection lng={lng} />;
    },
  },
  'admin-consumption-export': {
    render: async lng => {
      const { default: AdminConsumptionExportSection } =
        await import('./AdminConsumptionExportSection');
      return <AdminConsumptionExportSection lng={lng} />;
    },
  },
  'admin-broadcast': {
    render: async lng => {
      const { default: AdminBroadcastSection } = await import('./AdminBroadcastSection');
      return <AdminBroadcastSection lng={lng} />;
    },
  },

  // ---- Administration / AI & Connectors
  'admin-connectors': {
    render: async lng => {
      const { default: AdminConnectorsSection } = await import('./AdminConnectorsSection');
      return <AdminConnectorsSection lng={lng} />;
    },
  },
  'admin-llm-pricing': {
    render: async lng => {
      const { default: AdminLLMPricingSection } = await import('./AdminLLMPricingSection');
      return <AdminLLMPricingSection lng={lng} />;
    },
  },
  'admin-google-api-pricing': {
    render: async lng => {
      const { default: AdminGoogleApiPricingSection } =
        await import('./AdminGoogleApiPricingSection');
      return <AdminGoogleApiPricingSection lng={lng} />;
    },
  },
  'admin-image-pricing': {
    render: async lng => {
      const { default: AdminImagePricingSection } = await import('./AdminImagePricingSection');
      return <AdminImagePricingSection lng={lng} />;
    },
  },
  'admin-llm-config': {
    feature: 'llm-config',
    render: async lng => {
      const { default: AdminLLMConfigSection } = await import('./AdminLLMConfigSection');
      return <AdminLLMConfigSection lng={lng} />;
    },
  },
  'admin-voice-library': {
    feature: 'voice-library',
    render: async lng => {
      const { default: AdminVoiceLibrarySection } = await import('./AdminVoiceLibrarySection');
      return <AdminVoiceLibrarySection lng={lng} />;
    },
  },
  'admin-jev': {
    feature: 'llm-config',
    render: async lng => {
      const { default: AdminJevSection } = await import('./AdminJevSection');
      return <AdminJevSection lng={lng} />;
    },
  },

  // ---- Administration / Content & Extensions
  'admin-personalities': {
    render: async lng => {
      const { default: AdminPersonalitiesSection } = await import('./AdminPersonalitiesSection');
      return <AdminPersonalitiesSection lng={lng} />;
    },
  },
  'admin-skills': {
    feature: 'admin-skills',
    render: async lng => {
      const { AdminSkillsSection } = await import('./AdminSkillsSection');
      return <AdminSkillsSection lng={lng} />;
    },
  },
  'rag-spaces-admin': {
    feature: 'rag-spaces-admin',
    render: async lng => {
      const { default: AdminRAGSpacesSection } = await import('./AdminRAGSpacesSection');
      return <AdminRAGSpacesSection lng={lng} />;
    },
  },

  // ---- Administration / System
  'admin-capabilities': {
    render: async lng => {
      const { default: AdminCapabilitiesSection } = await import('./AdminCapabilitiesSection');
      return <AdminCapabilitiesSection lng={lng} />;
    },
  },
  'admin-registers': {
    render: async lng => {
      const { default: AdminRegistersSection } = await import('./AdminRegistersSection');
      return <AdminRegistersSection lng={lng} />;
    },
  },
  'admin-diagnostics': {
    render: async lng => {
      const { default: AdminDiagnosticsSection } = await import('./AdminDiagnosticsSection');
      return <AdminDiagnosticsSection lng={lng} />;
    },
  },
  'admin-public-demo-link': {
    render: async lng => {
      const { default: AdminPublicDemoLinkSection } = await import('./AdminPublicDemoLinkSection');
      return <AdminPublicDemoLinkSection lng={lng} />;
    },
  },
  'debug-settings': {
    render: async lng => {
      const { default: AdminDebugSettingsSection } = await import('./AdminDebugSettingsSection');
      return <AdminDebugSettingsSection lng={lng} />;
    },
  },
};
