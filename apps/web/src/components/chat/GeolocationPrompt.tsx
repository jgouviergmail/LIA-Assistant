'use client';

import { useState, useEffect, useCallback } from 'react';
import { MapPin, X, Navigation, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import { useGeolocation } from '@/hooks/useGeolocation';
import type { GeolocationPermission } from '@/hooks/useGeolocation';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';
import { GEOLOCATION_REACTIVATION_DISMISSED_KEY } from '@/lib/constants';
import {
  containsCurrentLocationPhrase as detectCurrentLocationPhrase,
  containsHomeLocationPhrase as detectHomeLocationPhrase,
  containsLocationQueryPhrase as detectLocationQueryPhrase,
} from '@/lib/location-detection';

/** Read the session-scoped proactive dismissal (safe without storage). */
function readProactiveDismissed(): boolean {
  try {
    return sessionStorage.getItem(GEOLOCATION_REACTIVATION_DISMISSED_KEY) === 'true';
  } catch {
    return false;
  }
}

/** Pure visibility decision for the phrase-triggered modes. */
function phrasePromptDecision(args: {
  isDismissed: boolean;
  permission: GeolocationPermission;
  isEnabled: boolean;
  hasCoordinates: boolean;
  hasLocationPhrase: boolean;
}): { show: boolean; hiddenReason: string | null } {
  if (args.isDismissed) return { show: false, hiddenReason: 'dismissed' };
  // Denied needs a browser-settings change, not a banner.
  if (args.permission === 'denied') return { show: false, hiddenReason: 'permission_denied' };
  // Enabled AND coordinates present: nothing to ask. (Enabled WITHOUT
  // coordinates keeps prompting — GPS off, timeout, expired cache.)
  if (args.isEnabled && args.hasCoordinates) {
    return { show: false, hiddenReason: 'coordinates_available' };
  }
  return { show: args.hasLocationPhrase, hiddenReason: null };
}

type BannerMode = 'reactivate' | 'retry' | 'enable';

/**
 * Per-mode banner content (decision table — keeps the component's render
 * free of nested ternaries). `reactivate` wins over `retry`: it explains WHY
 * the position is gone, which the generic wording does not.
 */
const BANNER_CONTENT: Record<
  BannerMode,
  {
    titleKey: string;
    descriptionKey: string;
    buttonKey: string;
    Icon: typeof Navigation;
    warningTone: boolean;
    buttonVariant: 'default' | 'outline';
  }
> = {
  reactivate: {
    titleKey: 'chat.geolocation.reactivate_title',
    descriptionKey: 'chat.geolocation.reactivate_description',
    buttonKey: 'chat.geolocation.reactivate_button',
    Icon: Navigation,
    warningTone: true,
    buttonVariant: 'default',
  },
  retry: {
    titleKey: 'chat.geolocation.retry_title',
    descriptionKey: 'chat.geolocation.retry_description',
    buttonKey: 'chat.geolocation.retry_button',
    Icon: RefreshCw,
    warningTone: true,
    buttonVariant: 'outline',
  },
  enable: {
    titleKey: 'chat.geolocation.prompt_title',
    descriptionKey: 'chat.geolocation.prompt_description',
    buttonKey: 'chat.geolocation.enable_button',
    Icon: Navigation,
    warningTone: false,
    buttonVariant: 'default',
  },
};

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
 * location-related phrases like "nearby" or "dans le coin" — and, since
 * 2026-08-16, PROACTIVELY when the browser permission fell back to `prompt`
 * while the user had opted in (typical iOS-standalone behavior after
 * inactivity): the native permission sheet requires a user gesture, so the
 * banner shows on chat open, before any typed phrase, and its button
 * supplies the gesture. That proactive mode is dismissable once per session
 * (`sessionStorage`) and takes precedence over the phrase-triggered modes.
 *
 * Phrase mode uses intelligent detection with:
 * - Text normalization (accents, case insensitive)
 * - Keyword matching with word boundaries
 * - Regex patterns for flexible phrase matching
 *
 * Phrase-mode visibility rules live in {@link phrasePromptDecision}.
 */
export function GeolocationPrompt({
  currentMessage,
  onGeolocationEnabled,
  className,
}: GeolocationPromptProps) {
  const { t, i18n } = useTranslation();
  const { isEnabled, permission, enable, isLoading, coordinates, refresh, needsReactivation } =
    useGeolocation();
  const [isDismissed, setIsDismissed] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [proactiveDismissed, setProactiveDismissed] = useState(readProactiveDismissed);

  // Determine if this is a "retry" scenario (enabled but no coordinates)
  const isRetryMode = isEnabled && !coordinates;

  // Proactive reactivation: the permission dropped back while opted in.
  // Independent of the typed message — this is the "before the user asks"
  // path (owner arbitration 2026-08-16, chat-only scope).
  const isReactivationMode = needsReactivation && !proactiveDismissed;

  // Get current language for detection (extract base language code from i18n instance)
  const currentLanguage = (i18n.language || 'fr').split('-')[0];

  // Check if message contains location phrases using reliable detection
  // Uses hardcoded patterns (synced with backend) instead of i18n for reliability
  const checkLocationPhrase = useCallback(
    (message: string): boolean => {
      if (!message.trim()) return false;
      // Current position, home, or "where am I" query phrases — all three
      // need geolocation (the query category was the missing one: "montre-moi
      // où je suis" never triggered this prompt).
      return (
        detectCurrentLocationPhrase(message, currentLanguage) ||
        detectHomeLocationPhrase(message, currentLanguage) ||
        detectLocationQueryPhrase(message, currentLanguage)
      );
    },
    [currentLanguage]
  );

  // Phrase-triggered visibility (the proactive mode bypasses this entirely).
  useEffect(() => {
    const decision = phrasePromptDecision({
      isDismissed,
      permission,
      isEnabled,
      hasCoordinates: !!coordinates,
      hasLocationPhrase: checkLocationPhrase(currentMessage),
    });

    if (decision.hiddenReason) {
      logger.debug('geolocation_prompt_hidden', {
        component: 'GeolocationPrompt',
        reason: decision.hiddenReason,
      });
    } else if (decision.show) {
      logger.info('geolocation_prompt_shown', {
        component: 'GeolocationPrompt',
        isRetryMode,
        isEnabled,
        hasCoordinates: !!coordinates,
        permission,
        messagePreview: currentMessage.substring(0, 50),
      });
    }

    setShowPrompt(decision.show);
  }, [
    currentMessage,
    isEnabled,
    isDismissed,
    permission,
    coordinates,
    isRetryMode,
    checkLocationPhrase,
  ]);

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
        isRetryMode ? t('chat.geolocation.retry_failed') : t('chat.geolocation.permission_denied')
      );
    }
  }, [enable, refresh, isRetryMode, isEnabled, coordinates, permission, t, onGeolocationEnabled]);

  // Reactivation button: the user gesture that reopens the native sheet.
  const handleReactivate = useCallback(async () => {
    logger.info('geolocation_prompt_action', {
      component: 'GeolocationPrompt',
      action: 'reactivate',
      permission,
    });
    const result = await enable();
    if (result) {
      toast.success(t('chat.geolocation.enabled_success'));
      onGeolocationEnabled?.();
    } else {
      toast.error(t('chat.geolocation.permission_denied'));
    }
  }, [enable, permission, t, onGeolocationEnabled]);

  // Handle dismiss — the proactive mode holds for the whole session, the
  // phrase mode only until the composer is cleared.
  const handleDismiss = useCallback(() => {
    if (isReactivationMode) {
      try {
        sessionStorage.setItem(GEOLOCATION_REACTIVATION_DISMISSED_KEY, 'true');
      } catch {
        // Storage unavailable — the in-memory state still hides it.
      }
      setProactiveDismissed(true);
      return;
    }
    setIsDismissed(true);
  }, [isReactivationMode]);

  // Reset dismissed state when message is cleared
  useEffect(() => {
    if (!currentMessage.trim()) {
      setIsDismissed(false);
    }
  }, [currentMessage]);

  if (!isReactivationMode && !showPrompt) {
    return null;
  }

  const mode: BannerMode = isReactivationMode ? 'reactivate' : isRetryMode ? 'retry' : 'enable';
  const content = BANNER_CONTENT[mode];
  const primaryAction = mode === 'reactivate' ? handleReactivate : handleEnable;
  const ButtonIcon = content.Icon;

  return (
    <div
      className={cn(
        'mx-4 mb-2 rounded-lg border p-3 animate-in slide-in-from-bottom-2 duration-200',
        content.warningTone ? 'border-warning/30 bg-warning/5' : 'border-primary/30 bg-primary/5',
        className
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'flex-shrink-0 rounded-full p-2',
            content.warningTone ? 'bg-warning/10' : 'bg-primary/10'
          )}
        >
          <MapPin
            className={cn('h-4 w-4', content.warningTone ? 'text-warning' : 'text-primary')}
          />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{t(content.titleKey)}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{t(content.descriptionKey)}</p>
          <div className="mt-2 flex items-center gap-2">
            <Button
              size="sm"
              onClick={primaryAction}
              disabled={isLoading}
              variant={content.buttonVariant}
              className="h-7 text-xs gap-1.5"
            >
              <ButtonIcon className={cn('h-3 w-3', isLoading && 'animate-spin')} />
              {t(content.buttonKey)}
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
          aria-label={t('chat.geolocation.dismiss_button')}
          className="flex-shrink-0 rounded-full p-1 hover:bg-muted transition-colors"
        >
          <X className="h-4 w-4 text-muted-foreground" />
        </button>
      </div>
    </div>
  );
}

export default GeolocationPrompt;
