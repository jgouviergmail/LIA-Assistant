'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { fallbackLng } from '@/i18n/settings';
import { getLanguageFromPath, buildLocalizedPath } from '@/utils/i18n-path-utils';
import Link from 'next/link';
import { MemoryToggle } from '@/components/memory-toggle';
import { VoiceToggle } from '@/components/voice-toggle';
import { TokensDisplayToggle } from '@/components/tokens-display-toggle';
import { ThemeToggle } from '@/components/theme-toggle';
import { LanguageSelector } from '@/components/LanguageSelector';
import { PersonalitySelector } from '@/components/PersonalitySelector';
import { ConnectorHealthAlert } from '@/components/connectors/ConnectorHealthAlert';
import { OnboardingTutorial } from '@/components/onboarding';
import { BroadcastProvider } from '@/lib/broadcast';
import { BroadcastModal } from '@/components/broadcast';
import { useTranslation } from '@/i18n/client';
import {
  LayoutDashboard,
  MessageSquare,
  Settings,
  HelpCircle,
  LogOut,
} from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { proxyGoogleImageUrl } from '@/lib/utils';
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
    `inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all hover:bg-primary/10 hover:text-primary hover:shadow-sm ${
      isActiveRoute(route)
        ? 'bg-primary/15 text-primary shadow-sm border border-primary/20'
        : 'text-foreground/60'
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

  if (!user) {
    return null;
  }

  return (
    <BroadcastProvider isAuthenticated={!!user}>
      <div className="min-h-screen bg-background">
        {/* OAuth Connector Health Alert (toast + modal) */}
        <ConnectorHealthAlert lng={lng} />

        {/* Admin Broadcast Modal */}
        <BroadcastModal lng={lng} />

        {/* Navbar - Enhanced Glassmorphism */}
        <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60 shadow-sm">
          <div className="w-full max-w-7xl mx-auto flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
            {/* Logo & Navigation */}
            <div className="flex items-center gap-8">
              <Link href={buildLocalizedPath('/dashboard', pathLng)} className="flex items-center gap-2 group">
                <div className="flex h-10 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary/80 shadow-md group-hover:shadow-lg transition-all">
                  <span className="text-sm font-bold text-primary-foreground">LIA</span>
                </div>
              </Link>
              <nav className="hidden md:flex items-center gap-1">
                <Link
                  href={buildLocalizedPath('/dashboard', pathLng)}
                  className={navLinkClass('')}
                >
                  <LayoutDashboard className="h-4 w-4" />
                  <span>{t('navigation.dashboard')}</span>
                </Link>
                <Link
                  href={buildLocalizedPath('/dashboard/chat', pathLng)}
                  className={navLinkClass('chat')}
                >
                  <MessageSquare className="h-4 w-4" />
                  <span>{t('navigation.chat')}</span>
                </Link>
                <Link
                  href={buildLocalizedPath('/dashboard/settings', pathLng)}
                  className={navLinkClass('settings')}
                >
                  <Settings className="h-4 w-4" />
                  <span>{t('navigation.settings')}</span>
                </Link>
                <Link
                  href={buildLocalizedPath('/dashboard/faq', pathLng)}
                  className={navLinkClass('faq')}
                >
                  <HelpCircle className="h-4 w-4" />
                  <span>{t('navigation.faq')}</span>
                </Link>
              </nav>
            </div>

            {/* User Actions */}
            <div className="flex items-center flex-1 md:flex-none">
              {/* Icons container - evenly spaced on mobile, normal gap on desktop */}
              <div className="flex items-center flex-1 justify-evenly md:justify-end md:gap-3">
                <MemoryToggle lng={lng} />
                <VoiceToggle lng={lng} />
                {/* TokensDisplayToggle - Desktop only */}
                <div className="hidden md:block">
                  <TokensDisplayToggle lng={lng} />
                </div>
                <ThemeToggle />
                <PersonalitySelector />
                <LanguageSelector currentLocale={lng} />
              </div>

              {/* User Profile - Clickable for logout */}
              <button
                onClick={logout}
                className="flex items-center gap-2 sm:gap-3 px-2 sm:px-3 py-1.5 rounded-lg bg-muted/50 backdrop-blur-sm cursor-pointer transition-colors hover:bg-destructive/10 hover:text-destructive ml-3"
                title={t('navigation.logout')}
              >
                {user.picture_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={proxyGoogleImageUrl(user.picture_url) || user.picture_url}
                    alt={user.full_name || user.email}
                    className="h-8 w-8 rounded-full object-cover ring-2 ring-primary/20 shadow-sm"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary to-primary/80 flex items-center justify-center ring-2 ring-primary/20 shadow-sm">
                    <span className="text-sm font-semibold text-primary-foreground">
                      {user.full_name?.[0]?.toUpperCase() || user.email[0].toUpperCase()}
                    </span>
                  </div>
                )}
                <div className="hidden lg:flex flex-col text-left">
                  {user.full_name && (
                    <span className="text-sm font-semibold leading-none">{user.full_name}</span>
                  )}
                  <span
                    className={`text-xs text-muted-foreground ${!user.full_name ? 'text-sm' : 'mt-1'}`}
                  >
                    {user.email}
                  </span>
                </div>
                <LogOut className="h-4 w-4 sm:ml-1" />
              </button>
            </div>
          </div>
        </header>

        {/* Main Content - Reduced top spacing, no bottom padding for full-page apps */}
        <main className="w-full max-w-7xl mx-auto pt-4 pb-0 px-4 sm:px-6 lg:px-8">{children}</main>

        {/* Onboarding Tutorial */}
        {showOnboarding && (
          <OnboardingTutorial
            lng={lng}
            open={showOnboarding}
            onComplete={handleOnboardingComplete}
          />
        )}
      </div>
    </BroadcastProvider>
  );
}
