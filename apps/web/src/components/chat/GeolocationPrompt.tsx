'use client';

import { useState, useEffect, useCallback } from 'react';
import { MapPin, X, Navigation, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import { useGeolocation } from '@/hooks/useGeolocation';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';
import {
  containsCurrentLocationPhrase as detectCurrentLocationPhrase,
  containsHomeLocationPhrase as detectHomeLocationPhrase,
} from '@/lib/location-detection';

interface GeolocationPromptProps {
  /** Current message being typed */
  currentMessage: string;
  /** Callback when geolocation is enabled */
  onGeolocationEnabled?: () => void;
  /** Additional class names */
  className?: string;
}

/**
 * A banner that prompts users to enable geolocation when they type
 * location-related phrases like "nearby" or "dans le coin".
 *
 * Uses intelligent detection with:
 * - Text normalization (accents, case insensitive)
 * - Keyword matching with word boundaries
 * - Regex patterns for flexible phrase matching
 *
 * Only shows when:
 * - Message contains location phrases
 * - Coordinates are NOT available (either not enabled OR enabled but no coords)
 * - Permission was not denied by browser
 * - User hasn't dismissed the banner this session
 */
export function GeolocationPrompt({
  currentMessage,
  onGeolocationEnabled,
  className,
}: GeolocationPromptProps) {
  const { t, i18n } = useTranslation();
  const { isEnabled, permission, enable, isLoading, coordinates, refresh } = useGeolocation();
  const [isDismissed, setIsDismissed] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);

  // Determine if this is a "retry" scenario (enabled but no coordinates)
  const isRetryMode = isEnabled && !coordinates;

  // Get current language for detection (extract base language code from i18n instance)
  const currentLanguage = (i18n.language || 'fr').split('-')[0];

  // Check if message contains location phrases using reliable detection
  // Uses hardcoded patterns (synced with backend) instead of i18n for reliability
  const checkLocationPhrase = useCallback(
    (message: string): boolean => {
      if (!message.trim()) return false;
      // Check for both current location and home location phrases
      return (
        detectCurrentLocationPhrase(message, currentLanguage) ||
        detectHomeLocationPhrase(message, currentLanguage)
      );
    },
    [currentLanguage]
  );

  // Check if we should show the prompt
  useEffect(() => {
    // Don't show if dismissed this session
    if (isDismissed) {
      logger.debug('geolocation_prompt_hidden', {
        component: 'GeolocationPrompt',
        reason: 'dismissed',
      });
      setShowPrompt(false);
      return;
    }

    // Don't show if permission was denied (user needs to change browser settings)
    if (permission === 'denied') {
      logger.debug('geolocation_prompt_hidden', {
        component: 'GeolocationPrompt',
        reason: 'permission_denied',
      });
      setShowPrompt(false);
      return;
    }

    // Don't show if geolocation is enabled AND coordinates are available
    // This is the key fix: show the prompt if enabled but no coordinates
    // (e.g., GPS disabled, timeout, cache expired, first visit after enabling)
    if (isEnabled && coordinates) {
      logger.debug('geolocation_prompt_hidden', {
        component: 'GeolocationPrompt',
        reason: 'coordinates_available',
        hasCoordinates: true,
      });
      setShowPrompt(false);
      return;
    }

    // Check if message contains location phrases using reliable hardcoded detection
    const hasLocationPhrase = checkLocationPhrase(currentMessage);

    if (hasLocationPhrase) {
      logger.info('geolocation_prompt_shown', {
        component: 'GeolocationPrompt',
        isRetryMode,
        isEnabled,
        hasCoordinates: !!coordinates,
        permission,
        messagePreview: currentMessage.substring(0, 50),
      });
    }

    setShowPrompt(hasLocationPhrase);
  }, [currentMessage, isEnabled, isDismissed, permission, coordinates, isRetryMode, checkLocationPhrase, currentLanguage]);

  // Handle enable/retry button click
  const handleEnable = useCallback(async () => {
    logger.info('geolocation_prompt_action', {
      component: 'GeolocationPrompt',
      action: isRetryMode ? 'retry' : 'enable',
      isEnabled,
      hasCoordinates: !!coordinates,
      permission,
    });

    // Use refresh if already enabled (retry mode), otherwise enable
    const result = isRetryMode ? await refresh() : await enable();

    if (result || (isRetryMode && coordinates)) {
      toast.success(t('chat.geolocation.enabled_success'));
      onGeolocationEnabled?.();
    } else {
      toast.error(
        isRetryMode
          ? t('chat.geolocation.retry_failed')
          : t('chat.geolocation.permission_denied')
      );
    }
  }, [enable, refresh, isRetryMode, isEnabled, coordinates, permission, t, onGeolocationEnabled]);

  // Handle dismiss
  const handleDismiss = useCallback(() => {
    setIsDismissed(true);
  }, []);

  // Reset dismissed state when message is cleared
  useEffect(() => {
    if (!currentMessage.trim()) {
      setIsDismissed(false);
    }
  }, [currentMessage]);

  if (!showPrompt) {
    return null;
  }

  // Select appropriate messages based on mode
  const title = isRetryMode
    ? t('chat.geolocation.retry_title')
    : t('chat.geolocation.prompt_title');

  const description = isRetryMode
    ? t('chat.geolocation.retry_description')
    : t('chat.geolocation.prompt_description');

  const buttonLabel = isRetryMode
    ? t('chat.geolocation.retry_button')
    : t('chat.geolocation.enable_button');

  const ButtonIcon = isRetryMode ? RefreshCw : Navigation;

  return (
    <div
      className={cn(
        'mx-4 mb-2 rounded-lg border p-3 animate-in slide-in-from-bottom-2 duration-200',
        isRetryMode
          ? 'border-warning/30 bg-warning/5'
          : 'border-primary/30 bg-primary/5',
        className
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'flex-shrink-0 rounded-full p-2',
            isRetryMode ? 'bg-warning/10' : 'bg-primary/10'
          )}
        >
          <MapPin className={cn('h-4 w-4', isRetryMode ? 'text-warning' : 'text-primary')} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          <div className="mt-2 flex items-center gap-2">
            <Button
              size="sm"
              onClick={handleEnable}
              disabled={isLoading}
              variant={isRetryMode ? 'outline' : 'default'}
              className="h-7 text-xs gap-1.5"
            >
              <ButtonIcon className={cn('h-3 w-3', isLoading && 'animate-spin')} />
              {buttonLabel}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleDismiss}
              className="h-7 text-xs text-muted-foreground"
            >
              {t('chat.geolocation.dismiss_button')}
            </Button>
          </div>
        </div>
        <button
          onClick={handleDismiss}
          className="flex-shrink-0 rounded-full p-1 hover:bg-muted transition-colors"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>
    </div>
  );
}

export default GeolocationPrompt;
