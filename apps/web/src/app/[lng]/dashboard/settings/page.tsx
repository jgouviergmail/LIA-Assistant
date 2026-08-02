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
import { ChatShortcutsSettings } from '@/components/settings/ChatShortcutsSettings';
import { OpenLoopsSection } from '@/components/settings/OpenLoopsSection';
import { PeerConnectionsSettings } from '@/components/settings/PeerConnectionsSettings';
import { CardsDisplaySettings } from '@/components/settings/CardsDisplaySettings';
import { SettingsGroupLabel } from '@/components/settings/SettingsGroupLabel';
import { SettingsTabsBar } from '@/components/settings/SettingsTabsBar';
import { SecuritySettings } from '@/components/settings/SecuritySettings';
import { DeviceSessionsSettings } from '@/components/settings/DeviceSessionsSettings';
import { AccountExportSettings } from '@/components/settings/AccountExportSettings';
import ConsumptionExportSection from '@/components/settings/ConsumptionExportSection';
import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useTranslation } from '@/i18n/client';
import { FeatureErrorBoundary } from '@/components/errors';
import { SettingsSearch } from '@/components/settings/SettingsSearch';
import { CatalogueInvalidationProvider } from '@/lib/catalogue-invalidation-context';
import { SETTINGS_SEARCH_META, type SettingsSearchAvailability } from '@/lib/settings-search';
import {
  SETTINGS_SECTIONS,
  isSettingsSectionToken,
  type SettingsSectionToken,
  type SettingsTab,
} from '@/lib/settings-sections';

interface SettingsPageProps {
  params: Promise<{ lng: string }>;
}

/**
 * A section the page has been asked to reveal.
 *
 * The token rather than the target: the tab, the accordion value AND the
 * translated title are all derivable from it, and the title is what an honest
 * "this section is not available" message needs.
 */
interface PendingSection {
  token: SettingsSectionToken;
  /**
   * Move focus onto the section's trigger.
   *
   * True only for a pick the reader just made in the search field. A deep link,
   * an OAuth return or the portrait shortcut must NOT steal focus: the reader
   * did not ask for it at that moment, and focus arriving asynchronously after
   * a page load is disorienting.
   */
  focus: boolean;
}

/**
 * First look after asking for a section, then how often, then for how long.
 *
 * The first delay is the accordion's opening animation — scrolling before the
 * item has height lands short. Everything after it exists because a section can
 * be absent for two very different reasons: it is gated off for this account
 * (`security-auth` without MFA, `telephony-calls` with no call), or its own
 * request has simply not answered yet (`heartbeat` and `briefing-grid` render
 * null while loading).
 *
 * Nothing distinguishes the two from here, which is why five seconds is a
 * courtesy and not a verdict: the message the reader eventually gets states the
 * OBSERVATION ("it is not showing here") and offers the gate as the likely
 * cause. Asserting unavailability outright would be a confident lie the day a
 * connection is slow.
 */
const SECTION_FIRST_LOOK_MS = 150;
const SECTION_POLL_MS = 120;
const SECTION_DEADLINE_MS = 5000;

export default function SettingsPage({ params }: SettingsPageProps) {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const { userAccessAvailable } = useDebugPanelEnabled();
  // The one instance flag a settings section actually reads before rendering
  // (`OpenLoopsSection`). The other `/config` flags are NOT consulted here: the
  // sections they name render regardless, and filtering the search on them
  // would hide something that is on the page.
  const { config } = useAppConfig();

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
  const [pendingSection, setPendingSection] = React.useState<PendingSection | null>(null);

  // Stable identity: `SettingsSearch` memoizes its whole index on this object,
  // and a fresh one per render would rebuild thirty entries every keystroke.
  const availability = React.useMemo<SettingsSearchAvailability>(
    () => ({
      isSuperuser: !!user?.is_superuser,
      // Mirrors `OpenLoopsSection` exactly, loading state included: while
      // `/config` is in flight the section is genuinely absent, and the index
      // rebuilds by itself when the answer lands.
      openLoopsEnabled: !!config?.features?.open_loops_enabled,
      peersEnabled: !!config?.features?.peers_enabled,
      debugUserAccess: userAccessAvailable,
    }),
    [
      user?.is_superuser,
      config?.features?.open_loops_enabled,
      config?.features?.peers_enabled,
      userAccessAvailable,
    ]
  );

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
    if (section && isSettingsSectionToken(section)) {
      // No focus move: the reader arrived from a link, they did not ask for the
      // caret to jump the moment the page settled.
      setPendingSection({ token: section, focus: false });
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
    setPendingSection({ token: 'connectors', focus: false });
    setShouldExpandConnectors(false);
  }, [shouldExpandConnectors]);

  // W2: honour a pending section target — activate its tab, expand its
  // accordion item, scroll to it, and (search only) put the caret on it. Which
  // accordion holds it depends on the tab AND on the layout: superusers get
  // three tabs (preferences / features / administration), everyone else two,
  // and the non-superuser preferences tab uses its own `allSections` state.
  //
  // A section can also fail to appear at all — eight of the thirty render
  // nothing under their own conditions. Rather than leaving the reader in front
  // of a page that did not move, the effect waits for it and then says so.
  React.useEffect(() => {
    if (!pendingSection) return;
    const { token, focus } = pendingSection;
    const { tab, accordionValue } = SETTINGS_SECTIONS[token];
    setActiveTab(tab);

    const expand = (prev: string[]) =>
      prev.includes(accordionValue) ? prev : [...prev, accordionValue];
    // A table keyed by `SettingsTab`, not an if/else chain. The chain used to
    // end in an `else` that swallowed anything unrecognised, and `tsc` now
    // proves the `administration` arm unreachable — the table has no
    // administration entry today. A `Record` keeps the mapping COMPLETE by
    // type: a fourth tab, or the phase-2 admin tokens, fail to compile instead
    // of silently expanding the wrong accordion.
    const expandIn: Record<SettingsTab, React.Dispatch<React.SetStateAction<string[]>>> = {
      // The non-superuser layout keeps the whole Preferences tab in one state.
      preferences: user?.is_superuser ? setAppearanceSections : setAllSections,
      features: setFeaturesSections,
      administration: setConnectorSections,
    };
    expandIn[tab](expand);

    const startedAt = Date.now();
    let timer = 0;

    const reveal = (node: HTMLElement) => {
      // `behavior: 'smooth'` in JS ignores `prefers-reduced-motion` — the same
      // trap `handleTabChange` documents a few lines below. Honour it here too.
      const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      node.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
      if (!focus) return;
      // The Radix accordion trigger — a disclosure button carrying
      // `aria-expanded`, pinned by `SettingsSection`'s own test. `preventScroll`
      // so focusing does not cancel the smooth scroll just started.
      const trigger =
        node.querySelector<HTMLElement>('button[aria-expanded]') ??
        node.querySelector<HTMLElement>('button');
      trigger?.focus({ preventScroll: true });
    };

    const settle = () => {
      const node = document.getElementById(`settings-section-${accordionValue}`);
      if (node) {
        reveal(node);
        setPendingSection(null);
        return;
      }
      if (Date.now() - startedAt >= SECTION_DEADLINE_MS) {
        // Named, not vague: the reader asked for a specific section and it is
        // not on their page. Saying nothing would leave a dead end that looks
        // like a broken link.
        toast.info(
          t('settings.search.unavailable', { section: t(SETTINGS_SEARCH_META[token].titleKey) })
        );
        setPendingSection(null);
        return;
      }
      timer = window.setTimeout(settle, SECTION_POLL_MS);
    };

    timer = window.setTimeout(settle, SECTION_FIRST_LOOK_MS);
    return () => window.clearTimeout(timer);
  }, [pendingSection, user?.is_superuser, t]);

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

  // Declared once, mounted by both layouts inside the sticky bar. Picking a
  // result is the ONE path that moves focus: the reader just acted, so landing
  // the caret on the section they asked for is what a keyboard user expects.
  const searchField = (
    <SettingsSearch
      lng={lng}
      availability={availability}
      onSelect={result => setPendingSection({ token: result.token, focus: true })}
    />
  );

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
          <SettingsTabsBar tabs={[preferencesTab, featuresTab, administrationTab]}>
            {searchField}
          </SettingsTabsBar>

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
              <ChatShortcutsSettings lng={lng} />

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
                <PortraitShortcut
                  onOpen={() => setPendingSection({ token: 'journals', focus: false })}
                />
              </FeatureErrorBoundary>
              <PersonalitySettings lng={lng} />
              <FeatureErrorBoundary feature="psyche">
                <PsycheSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="memory-settings">
                <MemorySettings lng={lng} />
              </FeatureErrorBoundary>
              <InterestsSettings lng={lng} />
              <OpenLoopsSection lng={lng} />
              <FeatureErrorBoundary feature="peer-connections">
                <PeerConnectionsSettings lng={lng} />
              </FeatureErrorBoundary>

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
          <SettingsTabsBar tabs={[preferencesTab, featuresTab]}>{searchField}</SettingsTabsBar>

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
              <ChatShortcutsSettings lng={lng} />

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
                <PortraitShortcut
                  onOpen={() => setPendingSection({ token: 'journals', focus: false })}
                />
              </FeatureErrorBoundary>
              <PersonalitySettings lng={lng} />
              <FeatureErrorBoundary feature="psyche">
                <PsycheSettings lng={lng} />
              </FeatureErrorBoundary>
              <FeatureErrorBoundary feature="memory-settings">
                <MemorySettings lng={lng} />
              </FeatureErrorBoundary>
              <InterestsSettings lng={lng} />
              <OpenLoopsSection lng={lng} />
              <FeatureErrorBoundary feature="peer-connections">
                <PeerConnectionsSettings lng={lng} />
              </FeatureErrorBoundary>

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
