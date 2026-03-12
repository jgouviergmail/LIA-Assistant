'use client';

import * as React from 'react';
import { CircleDollarSign } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';

interface TokensDisplayToggleProps {
  lng?: Language;
}

export function TokensDisplayToggle({ lng = 'fr' }: TokensDisplayToggleProps) {
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation(lng);
  const [mounted, setMounted] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(false);

  // Avoid hydration mismatch
  React.useEffect(() => {
    setMounted(true);
  }, []);

  const handleToggle = async () => {
    if (!user || isLoading) return;

    const newState = !user.tokens_display_enabled;
    setIsLoading(true);

    try {
      await apiClient.patch('/auth/me/tokens-display-preference', {
        tokens_display_enabled: newState,
      });

      // Refresh user to get updated state
      await refreshUser();

      toast.success(
        newState
          ? t('tokens_display.toggle.enabled')
          : t('tokens_display.toggle.disabled')
      );
    } catch (error) {
      logger.error('tokens_display_preference_update_failed', error as Error, { component: 'TokensDisplayToggle' });
      toast.error(t('common.error'));
    } finally {
      setIsLoading(false);
    }
  };

  // Show placeholder during SSR
  if (!mounted) {
    return (
      <Button variant="ghost" size="sm" className="w-11 h-11 px-0">
        <CircleDollarSign className="h-[1.2rem] w-[1.2rem]" />
        <span className="sr-only">{t('tokens_display.toggle.enable')}</span>
      </Button>
    );
  }

  const isEnabled = user?.tokens_display_enabled ?? false;

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-11 h-11 px-0"
      onClick={handleToggle}
      disabled={isLoading || !user}
      aria-label={isEnabled ? t('tokens_display.toggle.disable') : t('tokens_display.toggle.enable')}
      title={isEnabled ? t('tokens_display.toggle.tooltip_enabled') : t('tokens_display.toggle.tooltip_disabled')}
    >
      {isLoading ? (
        <LoadingSpinner className="h-[1.2rem] w-[1.2rem]" />
      ) : (
        <CircleDollarSign
          className={`h-[1.2rem] w-[1.2rem] transition-all ${
            isEnabled ? 'text-primary' : 'text-muted-foreground'
          }`}
        />
      )}
      <span className="sr-only">{isEnabled ? t('tokens_display.toggle.disable') : t('tokens_display.toggle.enable')}</span>
    </Button>
  );
}
