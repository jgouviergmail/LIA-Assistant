'use client';

import { useMemo } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useUserStatistics } from '@/hooks/useUserStatistics';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatNumber, formatEuro, getCycleDates } from '@/lib/format';
import { useTranslation } from '@/i18n/client';
import { useLiaGender } from '@/hooks/useLiaGender';
import {
  MessageSquare,
  Settings,
  Sparkles,
  Shield,
  CheckCircle2,
  TrendingUp,
  Zap,
  ArrowRight,
  Coins,
  Database,
  HelpCircle,
  Plug,
  Globe,
} from 'lucide-react';
import Image from 'next/image';
import { getGreetingPeriod } from '@/utils/timezone';
import { FeatureErrorBoundary } from '@/components/errors';

interface DashboardPageProps {
  params: Promise<{ lng: string }>;
}

export default function DashboardPage({ params }: DashboardPageProps) {
  const { user } = useAuth();
  const { statistics, isLoading: statsLoading } = useUserStatistics();
  const router = useRouter();
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const { liaImage, toggleGender: toggleLiaGender } = useLiaGender();

  // Get dynamic greeting based on user's timezone
  const greetingPeriod = getGreetingPeriod(user?.timezone);
  const greeting = t(`dashboard.greeting.${greetingPeriod}`, {
    name: user?.full_name || user?.email,
  });

  // Random tagline - changes on each page load
  const tagline = useMemo(() => {
    const taglines = t('dashboard.welcome_banner.taglines', { returnObjects: true }) as string[];
    const randomIndex = Math.floor(Math.random() * taglines.length);
    return taglines[randomIndex];
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lng]);

  return (
    <FeatureErrorBoundary feature="dashboard">
    <div className="space-y-8">
      {/* Header Section */}
      <div className="space-y-4">
        <h1 className="text-3xl tracking-tight text-center">{greeting}</h1>
      </div>

      {/* Main Feature Card - Chat with LIA */}
      <Card
        variant="elevated"
        className="w-full border-0 overflow-hidden relative rounded-xl h-[530px] cursor-pointer"
        onClick={toggleLiaGender}
      >
          <Image
            src={liaImage}
            alt="LIA"
            fill
            className="object-cover"
            priority
          />
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/30 to-background/60" />
          <CardContent className="flex flex-col items-center justify-between h-[530px] py-6 px-6 relative z-10">
            {/* Welcome Banner - Top */}
            <div className="text-center">
              <p
                className="text-2xl font-semibold text-foreground/90 leading-relaxed max-w-md drop-shadow-sm"
                dangerouslySetInnerHTML={{ __html: tagline }}
              />
            </div>

            {/* CTA Buttons - Bottom */}
            <div className="flex flex-col items-center gap-3 w-[250px]" onClick={(e) => e.stopPropagation()}>
              <Button
                onClick={() => router.push(`/${lng}/dashboard/settings?section=connectors`)}
                variant="default"
                size="lg"
                className="w-full"
              >
                <Plug className="h-5 w-5" />
                {t('dashboard.actions.connect')}
              </Button>
              <Button
                onClick={() => router.push(`/${lng}/dashboard/chat`)}
                variant="default"
                size="lg"
                className="w-full"
              >
                <Sparkles className="h-5 w-5" />
                {t('dashboard.actions.open_chat')}
                <ArrowRight className="h-4 w-4" />
              </Button>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Zap className="h-3.5 w-3.5 text-warning" />
                <span>{t('dashboard.main_feature.powered_by')}</span>
              </div>
            </div>
        </CardContent>
      </Card>

      {/* Quick Actions Grid - All using design tokens */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-semibold">{t('dashboard.quick_access.title')}</h2>
          <Badge variant="default" size="sm" icon={<TrendingUp className="h-3 w-3" />}>
            {t('dashboard.quick_access.optimized')}
          </Badge>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {/* Help Card - Primary color */}
          <Card
            variant="elevated"
            className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10 hover:shadow-xl transition-all"
          >
            <CardHeader className="space-y-4">
              <div className="flex flex-col items-center gap-3">
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary shadow-lg">
                  <HelpCircle className="h-7 w-7 text-primary-foreground" />
                </div>
                <Badge variant="default" size="sm">
                  {t('dashboard.quick_access.help.badge')}
                </Badge>
              </div>
              <div className="space-y-2 text-center">
                <CardTitle className="text-xl">{t('dashboard.quick_access.help.title')}</CardTitle>
                <CardDescription className="text-sm">
                  {t('dashboard.quick_access.help.description')}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Button
                onClick={() => router.push(`/${lng}/dashboard/faq`)}
                variant="softPrimary"
                size="sm"
                className="w-full"
              >
                <HelpCircle className="h-4 w-4" />
                {t('dashboard.quick_access.help.button')}
              </Button>
            </CardContent>
          </Card>

          {/* Settings Card - Warning/Accent color */}
          <Card
            variant="elevated"
            className="border-2 border-warning/20 bg-gradient-to-br from-warning/5 to-warning/10 hover:shadow-xl transition-all"
          >
            <CardHeader className="space-y-4">
              <div className="flex flex-col items-center gap-3">
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-warning shadow-lg">
                  <Settings className="h-7 w-7 text-warning-foreground" />
                </div>
                <Badge variant="warning" size="sm">
                  {t('dashboard.quick_access.settings_card.badge')}
                </Badge>
              </div>
              <div className="space-y-2 text-center">
                <CardTitle className="text-xl">
                  {t('dashboard.quick_access.settings_card.title')}
                </CardTitle>
                <CardDescription className="text-sm">
                  {t('dashboard.quick_access.settings_card.description')}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Button
                onClick={() => router.push(`/${lng}/dashboard/settings`)}
                variant="softWarning"
                size="sm"
                className="w-full"
              >
                <Settings className="h-4 w-4" />
                {t('dashboard.actions.settings')}
              </Button>
            </CardContent>
          </Card>

          {/* Security Card - Success color */}
          <Card
            variant="elevated"
            className="border-2 border-success/20 bg-gradient-to-br from-success/5 to-success/10 hover:shadow-xl transition-all"
          >
            <CardHeader className="space-y-4">
              <div className="flex flex-col items-center gap-3">
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-success shadow-lg">
                  <Shield className="h-7 w-7 text-success-foreground" />
                </div>
                <Badge variant="success" size="sm" icon={<CheckCircle2 className="h-3 w-3" />}>
                  {t('dashboard.quick_access.security.badge')}
                </Badge>
              </div>
              <div className="space-y-2 text-center">
                <CardTitle className="text-xl">
                  {t('dashboard.quick_access.security.title')}
                </CardTitle>
                <CardDescription className="text-sm">
                  {t('dashboard.quick_access.security.description')}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <Button variant="softSuccess" size="sm" className="w-full" disabled>
                <Shield className="h-4 w-4" />
                {t('dashboard.quick_access.security.button')}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Statistics Section - Token Usage & Cost Tracking */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">{t('dashboard.statistics.title')}</h2>
        <div className="grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
          {/* Messages - Current Month */}
          <Card
            variant="elevated"
            className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
                  {t('dashboard.statistics.messages.title')}
                </CardDescription>
                <MessageSquare className="h-5 w-5 text-primary" />
              </div>
              {!statsLoading && statistics && getCycleDates(statistics.current_cycle_start) && (
                <div className="text-xs text-muted-foreground mt-1">
                  {t('dashboard.statistics.cycle_dates', getCycleDates(statistics.current_cycle_start)!)}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-4xl font-bold text-primary">
                {statsLoading ? '-' : formatNumber(statistics?.cycle_messages || 0)}
              </div>
              {!statsLoading && statistics && (
                <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border/50">
                  <span>{t('dashboard.statistics.messages.total')}</span>
                  <span className="font-medium text-foreground/70">
                    {formatNumber(statistics.total_messages)}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Tokens - Current Month */}
          <Card
            variant="elevated"
            className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
                  {t('dashboard.statistics.tokens.title')}
                </CardDescription>
                <Database className="h-5 w-5 text-primary" />
              </div>
              {!statsLoading && statistics && getCycleDates(statistics.current_cycle_start) && (
                <div className="text-xs text-muted-foreground mt-1">
                  {t('dashboard.statistics.cycle_dates', getCycleDates(statistics.current_cycle_start)!)}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-4xl font-bold text-primary">
                {statsLoading
                  ? '-'
                  : formatNumber(
                      (statistics?.cycle_prompt_tokens || 0) +
                        (statistics?.cycle_completion_tokens || 0) +
                        (statistics?.cycle_cached_tokens || 0)
                    )}
              </div>
              {!statsLoading && statistics && (
                <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border/50">
                  <span>{t('dashboard.statistics.tokens.total')}</span>
                  <span className="font-medium text-foreground/70">
                    {formatNumber(
                      statistics.total_prompt_tokens +
                        statistics.total_completion_tokens +
                        statistics.total_cached_tokens
                    )}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Google API Requests - Current Month */}
          <Card
            variant="elevated"
            className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
                  {t('dashboard.statistics.google_api.title')}
                </CardDescription>
                <Globe className="h-5 w-5 text-primary" />
              </div>
              {!statsLoading && statistics && getCycleDates(statistics.current_cycle_start) && (
                <div className="text-xs text-muted-foreground mt-1">
                  {t('dashboard.statistics.cycle_dates', getCycleDates(statistics.current_cycle_start)!)}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-4xl font-bold text-primary">
                {statsLoading ? '-' : formatNumber(statistics?.cycle_google_api_requests || 0)}
              </div>
              {!statsLoading && statistics && (
                <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border/50">
                  <span>{t('dashboard.statistics.google_api.total')}</span>
                  <span className="font-medium text-foreground/70">
                    {formatNumber(statistics.total_google_api_requests)}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Cost EUR - Current Month */}
          <Card
            variant="elevated"
            className="border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-background hover:shadow-xl transition-all"
          >
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardDescription className="text-xs uppercase tracking-wider font-semibold text-primary">
                  {t('dashboard.statistics.cost.title')}
                </CardDescription>
                <Coins className="h-5 w-5 text-primary" />
              </div>
              {!statsLoading && statistics && getCycleDates(statistics.current_cycle_start) && (
                <div className="text-xs text-muted-foreground mt-1">
                  {t('dashboard.statistics.cycle_dates', getCycleDates(statistics.current_cycle_start)!)}
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-4xl font-bold text-primary">
                {statsLoading ? '-' : formatEuro(statistics?.cycle_cost_eur || 0, 2)}
              </div>
              {!statsLoading && statistics && (
                <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border/50">
                  <span>{t('dashboard.statistics.cost.total')}</span>
                  <span className="font-medium text-foreground/70">
                    {formatEuro(statistics.total_cost_eur, 2)}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
    </FeatureErrorBoundary>
  );
}
