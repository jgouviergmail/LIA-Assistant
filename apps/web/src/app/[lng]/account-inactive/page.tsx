'use client';

import { useEffect } from 'react';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Info, MailWarning } from 'lucide-react';
import { proxyGoogleImageUrl } from '@/lib/utils';

/**
 * Page displayed when a user logs in with a deactivated account.
 *
 * Note: This page is OUTSIDE the (auth) group because it requires a
 * different (wider) layout than the login/register pages.
 *
 * Compliance:
 * - Next.js 15: Dedicated route for business state
 * - WCAG 2.1 AA: role="alert", focus management, descriptive heading
 * - UX 2025: Clear message, next steps, empathy
 * - Responsive: Mobile-first with desktop adaptation
 * - Dark mode: Uses CSS theme tokens
 */
export default function AccountInactivePage() {
  const { user, isLoading, logout } = useAuth();
  const router = useLocalizedRouter();
  const { t } = useTranslation();

  // Redirect if user is active or not logged in
  useEffect(() => {
    if (!isLoading) {
      if (!user) {
        router.push('/login');
      } else if (user.is_active) {
        router.push('/dashboard');
      }
    }
  }, [user, isLoading, router]);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-lg text-muted-foreground">
          {t('account_inactive.loading')}
        </div>
      </div>
    );
  }

  // Don't render if redirecting
  if (!user || user.is_active) {
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 md:p-8">
      <Card
        className="w-full max-w-md md:max-w-2xl xl:max-w-3xl p-6 md:p-8 xl:p-10"
        role="alert"
        aria-live="assertive"
      >
        {/* Warning icon */}
        <div className="flex justify-center mb-6 md:mb-8">
          <div className="w-16 h-16 md:w-20 md:h-20 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
            <AlertTriangle className="w-8 h-8 md:w-10 md:h-10 text-orange-600 dark:text-orange-400" />
          </div>
        </div>

        {/* Title */}
        <h1 className="text-xl md:text-2xl xl:text-3xl font-bold text-foreground text-center mb-4 md:mb-6">
          {t('account_inactive.title')}
        </h1>

        {/* Main message */}
        <div className="space-y-4 md:space-y-6 mb-6 md:mb-8">
          <p className="text-center text-muted-foreground text-sm md:text-base">
            {t('account_inactive.message')}
          </p>

          {/* Info box */}
          <div className="bg-blue-50 dark:bg-blue-950/50 border-l-4 border-blue-500 p-4 md:p-5 rounded-r-lg">
            <div className="flex gap-3">
              <Info className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm md:text-base text-blue-700 dark:text-blue-300">
                <strong>{t('account_inactive.info_title')}</strong>{' '}
                {t('account_inactive.info_message')}
              </p>
            </div>
          </div>

          {/* Spam warning */}
          <div className="bg-amber-50 dark:bg-amber-950/50 border-l-4 border-amber-500 p-4 md:p-5 rounded-r-lg">
            <div className="flex gap-3">
              <MailWarning className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm md:text-base text-amber-700 dark:text-amber-300">
                <strong>{t('account_inactive.spam_warning_title')}</strong>{' '}
                {t('account_inactive.spam_warning_message')}
              </p>
            </div>
          </div>

          <p className="text-xs md:text-sm text-center text-muted-foreground">
            {t('account_inactive.help')}
          </p>
        </div>

        {/* User information */}
        <div className="bg-muted/50 rounded-lg p-4 md:p-5 mb-6 md:mb-8">
          <div className="flex items-center justify-center gap-4">
            {user.picture_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={proxyGoogleImageUrl(user.picture_url) || user.picture_url}
                alt={user.full_name || user.email}
                className="h-12 w-12 md:h-16 md:w-16 rounded-full object-cover ring-2 ring-border"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="h-12 w-12 md:h-16 md:w-16 rounded-full bg-primary/10 flex items-center justify-center ring-2 ring-border">
                <span className="text-primary text-lg md:text-2xl font-semibold">
                  {user.full_name?.[0]?.toUpperCase() || user.email[0].toUpperCase()}
                </span>
              </div>
            )}
            <div className="flex flex-col">
              {user.full_name && (
                <span className="text-sm md:text-lg font-medium text-foreground">
                  {user.full_name}
                </span>
              )}
              <span className="text-xs md:text-sm text-muted-foreground">{user.email}</span>
            </div>
          </div>
        </div>

        {/* Actions - side by side on desktop */}
        <div className="flex flex-col md:flex-row gap-3 md:gap-4">
          <Button onClick={logout} className="w-full" size="lg">
            {t('account_inactive.logout')}
          </Button>

          <Button
            onClick={() => window.location.reload()}
            variant="outline"
            className="w-full"
            size="lg"
          >
            {t('account_inactive.refresh')}
          </Button>
        </div>

        {/* Footer */}
        <p className="mt-6 md:mt-8 text-xs md:text-sm text-center text-muted-foreground">
          {t('account_inactive.footer')}
        </p>
      </Card>
    </div>
  );
}
