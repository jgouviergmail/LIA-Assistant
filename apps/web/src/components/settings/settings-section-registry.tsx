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

import { SpacesSettingsSection } from '@/components/spaces/SpacesSettingsSection';
import { ThemeSelector } from '@/components/theme-selector';
import type { Language } from '@/i18n/settings';
import type { SettingsSectionToken } from '@/lib/settings-sections';

import AdminBroadcastSection from './AdminBroadcastSection';
import AdminCapabilitiesSection from './AdminCapabilitiesSection';
import AdminRegistersSection from './AdminRegistersSection';
import AdminConnectorsSection from './AdminConnectorsSection';
import AdminConsumptionExportSection from './AdminConsumptionExportSection';
import AdminDebugSettingsSection from './AdminDebugSettingsSection';
import AdminDiagnosticsSection from './AdminDiagnosticsSection';
import AdminGoogleApiPricingSection from './AdminGoogleApiPricingSection';
import AdminImagePricingSection from './AdminImagePricingSection';
import AdminLLMConfigSection from './AdminLLMConfigSection';
import AdminLLMPricingSection from './AdminLLMPricingSection';
import { AdminMCPServersSettings } from './AdminMCPServersSettings';
import AdminPersonalitiesSection from './AdminPersonalitiesSection';
import AdminPublicDemoLinkSection from './AdminPublicDemoLinkSection';
import AdminRAGSpacesSection from './AdminRAGSpacesSection';
import { AdminSkillsSection } from './AdminSkillsSection';
import AdminUsersSection from './AdminUsersSection';
import { AdminUsageLimitsSection } from './AdminUsageLimitsSection';
import { AccountExportSettings } from './AccountExportSettings';
import { BriefingGridSettings } from './BriefingGridSettings';
import { CardsDisplaySettings } from './CardsDisplaySettings';
import { ChannelSettings } from './ChannelSettings';
import { ChatShortcutsSettings } from './ChatShortcutsSettings';
import ConsumptionExportSection from './ConsumptionExportSection';
import { DeviceSessionsSettings } from './DeviceSessionsSettings';
import { EyesStyleSettings } from './EyesStyleSettings';
import { FontSettings } from './FontSettings';
import { HabitsSettings } from './HabitsSettings';
import { HapticsSettings } from './HapticsSettings';
import { HealthMetricsSettings } from './HealthMetricsSettings';
import { HeartbeatSettings } from './HeartbeatSettings';
import { ImageGenerationSettings } from './ImageGenerationSettings';
import { InterestsSettings } from './InterestsSettings';
import { JournalsSettings } from './JournalsSettings';
import { LanguageSettings } from './LanguageSettings';
import { LocationSettings } from './LocationSettings';
import { MCPServersSettings } from './MCPServersSettings';
import { MemorySettings } from './MemorySettings';
import { NotificationSettings } from './NotificationSettings';
import { OpenLoopsSection } from './OpenLoopsSection';
import { PeerConnectionsSettings } from './PeerConnectionsSettings';
import { PersonalitySettings } from './PersonalitySettings';
import { PluginsSettings } from './PluginsSettings';
import { PsycheSettings } from './PsycheSettings';
import { ScheduledActionsSettings } from './ScheduledActionsSettings';
import { SecuritySettings } from './SecuritySettings';
import { SkillsSettings } from './SkillsSettings';
import TelephonyCallsSection from './TelephonyCallsSection';
import { MeetingsSettings } from './MeetingsSettings';
import { TimezoneSelector } from './TimezoneSelector';
import UserConnectorsSection from './UserConnectorsSection';
import { UserDebugSettings } from './UserDebugSettings';
import { VoiceModeSettings } from './VoiceModeSettings';

export interface SettingsSectionEntry {
  /** `FeatureErrorBoundary` label; absent = the section renders unwrapped. */
  feature?: string;
  /** The section, exactly as the accordion page used to mount it. */
  render: (lng: Language) => ReactElement;
}

export const SETTINGS_SECTION_REGISTRY: Readonly<
  Record<SettingsSectionToken, SettingsSectionEntry>
> = {
  // ---- Preferences / Personalization
  language: { render: lng => <LanguageSettings lng={lng} /> },
  timezone: { render: lng => <TimezoneSelector lng={lng} /> },
  location: { render: lng => <LocationSettings lng={lng} /> },
  theme: { render: lng => <ThemeSelector lng={lng} /> },
  font: { render: lng => <FontSettings lng={lng} /> },
  'eyes-style': { render: lng => <EyesStyleSettings lng={lng} /> },
  'display-mode': { render: lng => <CardsDisplaySettings lng={lng} /> },
  haptics: { render: lng => <HapticsSettings lng={lng} /> },
  'briefing-grid': { render: lng => <BriefingGridSettings lng={lng} /> },
  'chat-shortcuts': { render: lng => <ChatShortcutsSettings lng={lng} /> },

  // ---- Preferences / Notifications & Communication
  notifications: { render: lng => <NotificationSettings lng={lng} /> },
  channels: { feature: 'channels', render: lng => <ChannelSettings lng={lng} /> },

  // ---- Preferences / Security
  'security-auth': { feature: 'security', render: () => <SecuritySettings /> },
  'security-devices': { feature: 'security', render: () => <DeviceSessionsSettings /> },
  'security-export': { feature: 'security', render: () => <AccountExportSettings /> },

  // ---- Preferences / Voice & Media
  'voice-mode': { render: lng => <VoiceModeSettings lng={lng} /> },
  'image-generation': {
    feature: 'image-generation',
    render: lng => <ImageGenerationSettings lng={lng} />,
  },

  // ---- Preferences / Connections & Integrations
  connectors: { feature: 'connectors', render: lng => <UserConnectorsSection lng={lng} /> },
  'telephony-calls': {
    feature: 'telephony-calls',
    render: lng => <TelephonyCallsSection lng={lng} />,
  },
  'admin-mcp-servers': {
    feature: 'admin-mcp-servers',
    render: lng => <AdminMCPServersSettings lng={lng} />,
  },
  'mcp-servers': { feature: 'mcp-servers', render: lng => <MCPServersSettings lng={lng} /> },
  'debug-panel': { render: lng => <UserDebugSettings lng={lng} /> },

  // ---- Features / Identity & Memory
  personality: { render: lng => <PersonalitySettings lng={lng} /> },
  psyche: { feature: 'psyche', render: lng => <PsycheSettings lng={lng} /> },
  memories: { feature: 'memory-settings', render: lng => <MemorySettings lng={lng} /> },
  interests: { render: lng => <InterestsSettings lng={lng} /> },
  'open-loops': { render: lng => <OpenLoopsSection lng={lng} /> },
  habits: { feature: 'habits', render: lng => <HabitsSettings lng={lng} /> },
  'peer-connections': {
    feature: 'peer-connections',
    render: lng => <PeerConnectionsSettings lng={lng} />,
  },

  // ---- Features / Automation & Tracking
  heartbeat: { feature: 'heartbeat', render: lng => <HeartbeatSettings lng={lng} /> },
  'scheduled-actions': {
    feature: 'scheduled-actions',
    render: lng => <ScheduledActionsSettings lng={lng} />,
  },
  journals: { feature: 'journals', render: lng => <JournalsSettings lng={lng} /> },
  'health-metrics': {
    feature: 'health-metrics',
    render: lng => <HealthMetricsSettings lng={lng} />,
  },

  // ---- Features / Extensions & Data
  skills: { feature: 'skills', render: lng => <SkillsSettings lng={lng} /> },
  plugins: { feature: 'plugins', render: lng => <PluginsSettings lng={lng} /> },
  'rag-spaces': { feature: 'rag-spaces', render: lng => <SpacesSettingsSection lng={lng} /> },
  meetings: { feature: 'meetings', render: lng => <MeetingsSettings lng={lng} /> },
  'user-consumption-export': {
    feature: 'user-consumption-export',
    render: lng => <ConsumptionExportSection lng={lng} mode="user" />,
  },

  // ---- Administration / Users & Access
  'admin-users': { render: lng => <AdminUsersSection lng={lng} /> },
  'admin-usage-limits': {
    feature: 'usage-limits',
    render: lng => <AdminUsageLimitsSection lng={lng} />,
  },
  'admin-consumption-export': { render: lng => <AdminConsumptionExportSection lng={lng} /> },
  'admin-broadcast': { render: lng => <AdminBroadcastSection lng={lng} /> },

  // ---- Administration / AI & Connectors
  'admin-connectors': { render: lng => <AdminConnectorsSection lng={lng} /> },
  'admin-llm-pricing': { render: lng => <AdminLLMPricingSection lng={lng} /> },
  'admin-google-api-pricing': { render: lng => <AdminGoogleApiPricingSection lng={lng} /> },
  'admin-image-pricing': { render: lng => <AdminImagePricingSection lng={lng} /> },
  'admin-llm-config': { feature: 'llm-config', render: lng => <AdminLLMConfigSection lng={lng} /> },

  // ---- Administration / Content & Extensions
  'admin-personalities': { render: lng => <AdminPersonalitiesSection lng={lng} /> },
  'admin-skills': { feature: 'admin-skills', render: lng => <AdminSkillsSection lng={lng} /> },
  'rag-spaces-admin': {
    feature: 'rag-spaces-admin',
    render: lng => <AdminRAGSpacesSection lng={lng} />,
  },

  // ---- Administration / System
  'admin-capabilities': { render: lng => <AdminCapabilitiesSection lng={lng} /> },
  'admin-registers': { render: lng => <AdminRegistersSection lng={lng} /> },
  'admin-diagnostics': { render: lng => <AdminDiagnosticsSection lng={lng} /> },
  'admin-public-demo-link': { render: lng => <AdminPublicDemoLinkSection lng={lng} /> },
  'debug-settings': { render: lng => <AdminDebugSettingsSection lng={lng} /> },
};
