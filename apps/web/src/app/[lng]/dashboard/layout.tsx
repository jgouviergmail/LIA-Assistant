'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useLastKnownLocationSync } from '@/hooks/useLastKnownLocationSync';
import { fallbackLng } from '@/i18n/settings';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';
import Link from 'next/link';
import { ExecutionModeToggle } from '@/components/execution-mode-toggle';
import { VoiceToggle } from '@/components/voice-toggle';
import { TokensDisplayToggle } from '@/components/tokens-display-toggle';
import { ThemeToggle } from '@/components/theme-toggle';
import { LanguageSelector } from '@/components/LanguageSelector';
import { PersonalitySelector } from '@/components/PersonalitySelector';
import { ConnectorHealthAlert } from '@/components/connectors/ConnectorHealthAlert';
import { OnboardingTutorial } from '@/components/onboarding';
import { CompanionPresence } from '@/components/companion/CompanionPresence';
import { BroadcastProvider } from '@/lib/broadcast';
import { BroadcastModal } from '@/components/broadcast';
import {
  MeetingRecorderBannerSlot,
  MeetingRecorderProvider,
} from '@/components/meetings/MeetingRecorderProvider';
import {
  MeetingRecorderControl,
  RecorderAwareMobileNavMenu,
} from '@/components/meetings/MeetingRecorderControl';
import { useAppConfig } from '@/hooks/useAppConfig';
import { destinationPath, visibleDestinations } from '@/lib/dashboard-nav';
import type { DashboardDestination } from '@/lib/dashboard-nav';
import { useTranslation } from '@/i18n/client';
import {
  Bell,
  ClipboardList,
  LayoutDashboard,
  Users,
  MessageSquare,
  Settings,
  HelpCircle,
  LogOut,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

/**
 * Icon per destination segment — presentation-only concern, so it lives with
 * the renderer, not in the destinations table (which the mobile menu shares
 * and renders without icons). Completeness is enforced by the type: a new
 * segment fails to compile until it gets an icon.
 */
const DESTINATION_ICONS: Record<DashboardDestination['segment'], typeof LayoutDashboard> = {
  '': LayoutDashboard,
  chat: MessageSquare,
  relations: Users,
  meetings: ClipboardList,
  notifications: Bell,
  settings: Settings,
  faq: HelpCircle,
};
interface DashboardLayoutProps {
  children: React.ReactNode;
  params: Promise<{ lng: string }>;
}

export default function DashboardLayout({ children, params }: DashboardLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isLoading, logout } = useAuth();
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  // ADR-258: the recorder lives here so a recording survives navigation.
  const { config: appConfig } = useAppConfig(Boolean(user));
  // ADR-258: the meetings destination exists only where the instance offers
  // the feature — the same list feeds the desktop nav and the mobile menu.
  const destinations = visibleDestinations(appConfig?.features);
  // Keep the backend's last-known location fed wherever the user navigates
  // (opt-in and throttle enforced inside; inert for anonymous visitors).
  useLastKnownLocationSync();
  // Onboarding tutorial state
  const [showOnboarding, setShowOnboarding] = useState(false);

  // Use pathname-extracted language for nav detection (immediate, no async delay)
  // This avoids the async timing issue with useLanguageParam
  const pathLng = pathname ? getLanguageFromPath(pathname) : fallbackLng;
  const basePath = buildLocalizedPath('/dashboard', pathLng);

  // Check if a nav route is active by comparing pathname directly
  const isActiveRoute = (route: string): boolean => {
    if (!pathname) return false;

    if (route === '') {
      // Dashboard home: active only when exactly at /[lng]/dashboard (with or without trailing slash)
      return pathname === basePath || pathname === `${basePath}/`;
    }

    // Sub-routes: check if pathname starts with /[lng]/dashboard/[route]
    const targetPath = `${basePath}/${route}`;
    return pathname === targetPath || pathname.startsWith(`${targetPath}/`);
  };

  // Nav link classes based on active state (route = 'chat', 'settings', 'faq', or '' for home)
  const navLinkClass = (route: string) =>
    `inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-all hover:bg-primary/10 hover:text-primary hover:shadow-sm ${
      isActiveRoute(route)
        ? 'bg-primary/15 text-primary shadow-sm border border-primary/20'
        : // muted-foreground is the AA-proven de-emphasis token; an alpha of
          // foreground (/60) composites below 4.5:1 on the page background.
          'text-muted-foreground'
    }`;

  useEffect(() => {
    if (!isLoading && pathLng) {
      if (!user) {
        // User not logged in -> redirect to login
        router.push(buildLocalizedPath('/login', pathLng));
      } else if (!user.is_active) {
        // Deactivated user -> information page
        router.push(buildLocalizedPath('/account-inactive', pathLng));
      }
    }
  }, [user, isLoading, router, pathLng]);

  // Show onboarding tutorial for users who haven't completed it
  useEffect(() => {
    if (user && !user.onboarding_completed) {
      setShowOnboarding(true);
    }
  }, [user]);

  // Handler for onboarding completion
  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <LoadingSpinner size="xl" />
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  // Nothing is rendered while a redirect is in flight. For an account awaiting
  // activation this is not cosmetic: the shell below mounts the broadcast
  // provider and the navbar, which each open an EventSource on
  // /notifications/stream, plus the pages' polling hooks and the avatar proxy.
  // The server answers 403 to every one of them, and EventSource cannot read a
  // status — a 403 reaches `onerror` bare, so the hook replays a permanent
  // verdict as if it were a dropped connection, five times.
  //
  // Measured over 7 days in production for five verified-but-not-yet-activated
  // accounts (225 calls in one day for one of them): 82 on /notifications/stream,
  // 57 on /agents/runs/active, 56 on the avatar proxy, 40 on broadcasts/unread,
  // 35 on /personalities. Four of the five had signed up in the previous three
  // days — this is the standard entry path, and it looks like a broken app.
  // A component that never mounts cannot poll.
  if (!user || !user.is_active) {
    return null;
  }

  return (
    <BroadcastProvider isAuthenticated={!!user}>
      {/* SEO: Prevent search engines and AI bots from indexing authenticated pages */}
      <meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex" />

      {/* ADR-258/259: the recorder lives ABOVE the header so a recording
          survives navigation and the header's controls can read it. */}
      <MeetingRecorderProvider lng={lng} enabled={appConfig?.features?.meetings_enabled ?? false}>
        <div className="min-h-screen bg-background">
          {/* Admin Broadcast Modal */}
          <BroadcastModal lng={lng} />

          {/* Navbar - Enhanced Glassmorphism */}
          <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60 shadow-sm">
            <div className="w-full max-w-7xl mx-auto flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
              {/* Logo & Navigation. `min-w-0` makes THIS group the one that
                yields when the row is tight, so the trailing controls — the
                logout button in particular — are never pushed off-screen. */}
              <div className="flex min-w-0 items-center gap-4 xl:gap-8">
                {/* A2: below `lg` the nav below is hidden, so the logo becomes
                  the way to every page instead of a dead "go home" link.
                  Two exclusive elements, never one changing role — a link at
                  one width and a button at another cannot announce itself.
                  R01 moved the boundary from `md` to `lg`: with five
                  destinations the fr/de/es/it labels clip between 768 and
                  1024 px (measured by dashboard-header-reachability). */}
                <div className="lg:hidden">
                  <RecorderAwareMobileNavMenu
                    lng={lng}
                    buildHref={route => buildLocalizedPath(route, pathLng)}
                    translate={t}
                    isActiveRoute={isActiveRoute}
                    triggerLabel={t('common.menu')}
                    destinations={destinations}
                  />
                </div>
                <Link
                  href={buildLocalizedPath('/dashboard', pathLng)}
                  className="hidden shrink-0 items-center gap-2 group lg:flex"
                >
                  <div className="flex h-10 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/80 shadow-md group-hover:shadow-lg transition-all">
                    <span className="text-sm font-bold text-primary-foreground">LIA</span>
                  </div>
                </Link>
                {/* R01: rendered from DASHBOARD_DESTINATIONS — the same table the
                  mobile menu maps, as dashboard-nav.ts always claimed. The
                  hand-maintained copy here was the drift this kills. */}
                <nav className="hidden min-w-0 lg:flex items-center gap-1">
                  {destinations.map(({ segment, labelKey }) => {
                    const Icon = DESTINATION_ICONS[segment];
                    return (
                      <Link
                        key={segment || 'home'}
                        href={buildLocalizedPath(destinationPath(segment), pathLng)}
                        className={navLinkClass(segment)}
                        aria-current={isActiveRoute(segment) ? 'page' : undefined}
                        aria-label={t(labelKey)}
                        title={t(labelKey)}
                      >
                        {/* Below `xl` the row shows ICONS only. Six labels are
                          163 px wider than five in German (measured in the
                          app's font), and five already clipped between 768 and
                          1024 px — the reason this nav starts at `lg` at all.
                          The SEVENTH (meetings, ADR-258) was paid for on the
                          controls side: the language shows its flag alone and
                          the personality title waits for `2xl`. The label stays
                          the accessible name, so nothing is lost for assistive
                          technology or on hover. */}
                        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                        <span className="hidden xl:inline">{t(labelKey)}</span>
                      </Link>
                    );
                  })}
                </nav>
              </div>

              {/* User Actions. `shrink-0` on the whole group: when the nav and
                the control labels show together the row used to overflow —
                silently, because the root is `overflow-x: hidden`. Since R01
                the nav needs `lg`, so the tight band moved to 1024–1280 px.
                Pinned by the header-reachability spec. */}
              <div className="flex shrink-0 items-center flex-1 lg:flex-none">
                {/* Icons container - evenly spaced while the logo-menu layout is
                  active (below `lg` since R01), tighter once the nav is back. */}
                <div className="flex items-center flex-1 justify-evenly lg:justify-end lg:gap-1 xl:gap-3">
                  <ExecutionModeToggle lng={lng} />
                  {/* ADR-259: record / stop a meeting from any page. Below `lg`
                    the logo menu carries the same command (no width for a
                    seventh control on a phone — measured). */}
                  <div className="hidden lg:block">
                    <MeetingRecorderControl lng={lng} />
                  </div>
                  <VoiceToggle lng={lng} />
                  {/* Token counters are observation, not action: they only earn
                    their width once the row has room to spare. That moved from
                    `xl` to `2xl` when a SIXTH destination joined the nav —
                    measured at 1280 px in German, the last nav link and the
                    first control overlapped, and the counters are the one
                    element in the row nobody navigates with. */}
                  <div className="hidden 2xl:block">
                    <TokensDisplayToggle lng={lng} />
                  </div>
                  <ThemeToggle />
                  <PersonalitySelector />
                  <LanguageSelector currentLocale={lng} />
                </div>

                {/* Logout button — never compressible: signing out must stay
                  possible at every width. */}
                <button
                  onClick={logout}
                  className="flex shrink-0 items-center justify-center h-11 w-11 max-[380px]:h-9 max-[380px]:w-9 rounded-lg bg-destructive text-destructive-foreground cursor-pointer transition-colors hover:bg-destructive/90 ml-2 xl:ml-3 shadow-sm"
                  title={t('navigation.logout')}
                  aria-label={t('navigation.logout')}
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
          </header>

          {/* OAuth connector health: the persistent banner renders HERE, under
            the sticky header and above the page, while the modal it ships
            with is portalled and unaffected by this position. */}
          <ConnectorHealthAlert lng={lng} />

          {/* Main Content - Reduced top spacing, no bottom padding for full-page apps */}
          <main className="w-full max-w-7xl mx-auto pt-4 pb-0 px-4 sm:px-6 lg:px-8">
            {/* The recording banner: sticky under the header, on every page, so
              the capture can always be seen and stopped (ADR-259). */}
            <MeetingRecorderBannerSlot lng={lng} />
            {children}
          </main>

          {/* Onboarding Tutorial */}
          {showOnboarding && (
            <OnboardingTutorial
              lng={lng}
              open={showOnboarding}
              onComplete={handleOnboardingComplete}
            />
          )}

          {/* Floating companion — follows across dashboard pages, hidden on chat */}
          <CompanionPresence isAuthenticated={!!user} />
        </div>
      </MeetingRecorderProvider>
    </BroadcastProvider>
  );
}
