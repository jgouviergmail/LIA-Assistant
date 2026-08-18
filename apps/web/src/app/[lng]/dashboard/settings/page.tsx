'use client';

/**
 * Settings — master-detail shell.
 *
 * A rail of every visible section (grouped by tab and group, one activation
 * away at all times) beside a pane that mounts ONE section, resolved through
 * `SETTINGS_SECTION_REGISTRY`. With no selection the pane shows the overview
 * cards; below `lg` the rail itself is the landing and the pane takes over
 * the screen with a back control (drill-down).
 *
 * The page renders from the tables (`SETTINGS_SECTIONS` order, shell model
 * groups) — it hand-lists nothing, so a section exists here if and only if
 * the tables declare it, for both audiences at once. The former page spelled
 * out two full layouts (~330 duplicated lines) and stacked 51 collapsed
 * accordions; the section components themselves are unchanged.
 *
 * ## URL contract
 *
 * `?section=<token>` is both the deep-link API (17+ callers via
 * `settingsSectionHref`, OAuth returns, raw links) and the selection state:
 * picking a section writes it with `history.replaceState`, so a reload or a
 * share lands on the same pane; the overview clears it. An unknown token is
 * dropped from the URL and lands on the overview.
 */

import React from 'react';
import { toast } from 'sonner';

import { APP_VERSION } from '@/lib/version';
import { useAuth } from '@/hooks/useAuth';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useSearchParams } from 'next/navigation';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import { MCP_OAUTH_TOAST, resolveMcpOAuthOutcome } from '@/lib/mcp-oauth-callback';
import { FeatureErrorBoundary } from '@/components/errors';
import { PortraitShortcut } from '@/components/settings/PortraitShortcut';
import { SettingsOverview } from '@/components/settings/SettingsOverview';
import { SettingsPane } from '@/components/settings/SettingsPane';
import { SettingsRail } from '@/components/settings/SettingsRail';
import { SettingsSearch } from '@/components/settings/SettingsSearch';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import { useTranslation } from '@/i18n/client';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import { buildSettingsShellModel } from '@/lib/settings-shell-model';
import { isSettingsSectionToken, type SettingsSectionToken } from '@/lib/settings-sections';
import { cn } from '@/lib/utils';

interface SettingsPageProps {
  params: Promise<{ lng: string }>;
}

/** Rewrite `?section=` in place — selection state, not navigation. */
function writeSectionParam(token: SettingsSectionToken | null): void {
  const url = new URL(window.location.href);
  if (token) {
    url.searchParams.set('section', token);
  } else {
    url.searchParams.delete('section');
  }
  window.history.replaceState({}, '', url.toString());
}

export default function SettingsPage({ params }: SettingsPageProps) {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const { userAccessAvailable } = useDebugPanelEnabled();
  // The one instance flag a settings section actually reads before rendering
  // (`OpenLoopsSection`). The other `/config` flags are NOT consulted here: the
  // sections they name render regardless, and filtering the shell on them
  // would hide something the pane can show.
  const { config } = useAppConfig();

  /** Section shown in the pane; null = the overview. */
  const [active, setActive] = React.useState<SettingsSectionToken | null>(null);
  /** Monotonic counter: each search pick asks the pane for one focus move. */
  const [focusRequest, setFocusRequest] = React.useState(0);

  // Track if OAuth callback toast has been shown (prevents duplicate toasts)
  const oauthToastShownRef = React.useRef(false);

  // Stable identity: `SettingsSearch` memoizes its whole index on this object,
  // and a fresh one per render would rebuild fifty entries every keystroke.
  const availability = React.useMemo<SettingsSearchAvailability>(
    () => ({
      isSuperuser: !!user?.is_superuser,
      // Mirrors `OpenLoopsSection` exactly, loading state included: while
      // `/config` is in flight the section is genuinely absent, and the shell
      // rebuilds by itself when the answer lands.
      openLoopsEnabled: !!config?.features?.open_loops_enabled,
      habitsEnabled: !!config?.features?.habits_enabled,
      peersEnabled: !!config?.features?.peers_enabled,
      debugUserAccess: userAccessAvailable,
    }),
    [
      user?.is_superuser,
      config?.features?.open_loops_enabled,
      config?.features?.habits_enabled,
      config?.features?.peers_enabled,
      userAccessAvailable,
    ]
  );

  const model = React.useMemo(() => buildSettingsShellModel(availability), [availability]);

  const openSection = React.useCallback(
    (token: SettingsSectionToken, { focus = false }: { focus?: boolean } = {}) => {
      setActive(token);
      if (focus) setFocusRequest(count => count + 1);
      writeSectionParam(token);
      // Land at the top of the pane. Instant, not smooth: `behavior: 'smooth'`
      // in JS ignores `prefers-reduced-motion`.
      window.scrollTo({ top: 0 });
    },
    []
  );

  const closeSection = React.useCallback(() => {
    setActive(null);
    writeSectionParam(null);
    window.scrollTo({ top: 0 });
  }, []);

  // `?section=` arrivals — a deep link, the starter checklist, a briefing
  // card, an OAuth return. One firing per router navigation: our own
  // `history.replaceState` writes do not touch the router's search params.
  React.useEffect(() => {
    const section = searchParams.get('section');
    if (!section) {
      // A router navigation to the BARE settings URL — the dashboard nav
      // entry, clicked while a pane is open — must land on the overview.
      // (Our own `replaceState` cleanup never reaches here: it does not touch
      // the router's search params.)
      setActive(null);
      return;
    }
    if (isSettingsSectionToken(section)) {
      // No focus move: the reader arrived from a link, they did not ask for
      // the caret to jump the moment the page settled.
      setActive(section);
      return;
    }
    // Unknown token: land on the overview and drop it from the URL so a
    // reload does not replay the dead end.
    writeSectionParam(null);
  }, [searchParams]);

  // OAuth callback toasts (connectors + MCP), verbatim behaviour of the
  // accordion page — landing on the connectors section is now a pane
  // selection instead of a tab + accordion expansion.
  React.useEffect(() => {
    const connectorAdded = searchParams.get('connector_added');
    const connectorType = searchParams.get('connector_type');
    const error = searchParams.get('error');

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

      // Land on the connectors pane (no page reload — the section refetches).
      setActive('connectors');
      writeSectionParam('connectors');
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
    const mcpOAuthOutcome = resolveMcpOAuthOutcome(searchParams.get('mcp_oauth'));
    if (mcpOAuthOutcome && !oauthToastShownRef.current) {
      oauthToastShownRef.current = true;
      const { kind, key } = MCP_OAUTH_TOAST[mcpOAuthOutcome];
      toast[kind](t(key));
      // Clean URL params
      const url = new URL(window.location.href);
      url.searchParams.delete('mcp_oauth');
      url.searchParams.delete('server_id');
      url.searchParams.delete('error');
      window.history.replaceState({}, '', url.toString());
    }
  }, [searchParams, t]);

  if (!user) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('settings.title')}</h1>
        <p className="mt-2 text-muted-foreground">{t('settings.subtitle')}</p>
      </div>

      {/* Default stretch alignment on purpose: the aside must be as tall as
          the row for its sticky child to have travel room — `items-start`
          would clamp it to the rail's own height and the rail would scroll
          away with the page (measured in the browser, first e2e pass). */}
      <div className="lg:flex lg:gap-8">
        {/* The rail — the landing screen below `lg`, a sticky sidebar above. */}
        <aside className={cn('lg:w-64 lg:shrink-0', active && 'hidden lg:block')}>
          <div className="space-y-4 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto lg:pb-4 lg:pr-1">
            <SettingsSearch
              lng={lng}
              availability={availability}
              onSelect={result => openSection(result.token, { focus: true })}
            />
            <SettingsRail lng={lng} model={model} activeToken={active} onSelect={openSection} />
          </div>
        </aside>

        {/* The pane — one open section, or the overview cards. */}
        <div className={cn('min-w-0 flex-1', !active && 'hidden lg:block')}>
          {active ? (
            <SettingsPane
              lng={lng}
              token={active}
              availability={availability}
              onBack={closeSection}
              focusRequest={focusRequest}
            />
          ) : (
            <SettingsOverview lng={lng} model={model} onSelect={openSection}>
              {/* QW-10: "What LIA understands about you" — jumps to the
                  portrait inside Journals (renders only with a portrait). */}
              <FeatureErrorBoundary feature="journals">
                <PortraitShortcut onOpen={() => openSection('journals')} />
              </FeatureErrorBoundary>
            </SettingsOverview>
          )}
        </div>
      </div>

      {/* Version */}
      <p className="text-xs text-muted-foreground text-center pt-4">v{APP_VERSION}</p>
    </div>
  );
}
