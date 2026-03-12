'use client';

import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { Check, Globe, Info } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import { toast } from 'sonner';
import {
  getBrowserTimezone,
  formatTimezoneDisplay,
  getCurrentTimeInTimezone,
} from '@/utils/timezone';
import { logger } from '@/lib/logger';
import apiClient from '@/lib/api-client';
import { type User } from '@/lib/auth';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

export function TimezoneSelector({ lng, collapsible = true }: BaseSettingsProps) {
  const { user, refreshUser } = useAuth();
  const { t } = useTranslation(lng);
  const [timezones, setTimezones] = useState<Record<string, string[]>>({});
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTimezone, setSelectedTimezone] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const [browserTimezone, setBrowserTimezone] = useState<string | null>(null);

  // Fetch timezones from API
  useEffect(() => {
    const fetchTimezones = async () => {
      try {
        logger.info('Fetching timezones from API', { component: 'TimezoneSelector' });
        const data = await apiClient.get<Record<string, string[]>>('/users/timezones');
        logger.info('Timezones fetched successfully', {
          component: 'TimezoneSelector',
          count: Object.keys(data).length,
        });
        setTimezones(data);
      } catch (error) {
        logger.error(
          'Failed to fetch timezones',
          error instanceof Error ? error : new Error(String(error))
        );
      }
    };

    fetchTimezones();
  }, []);

  // Detect browser timezone and set current user timezone
  useEffect(() => {
    setMounted(true);
    const detected = getBrowserTimezone();
    setBrowserTimezone(detected);

    logger.info('TimezoneSelector mounted', {
      component: 'TimezoneSelector',
      userId: user?.id,
      userTimezone: user?.timezone,
      browserTimezone: detected,
    });

    if (user?.timezone) {
      setSelectedTimezone(user.timezone);
    }
  }, [user]);

  // Mutation hook for updating timezone
  const { mutate: updateTimezone, loading: updating } = useApiMutation<{ timezone: string }, User>({
    method: 'PATCH',
    componentName: 'TimezoneSelector',
    onSuccess: async updatedUser => {
      toast.success(t('settings.timezone.update_success'));

      // Show info about conversation history
      toast.info(t('settings.timezone.history_info'), {
        duration: 6000,
      });

      // Refresh user context
      await refreshUser?.();
      if (updatedUser.timezone) {
        setSelectedTimezone(updatedUser.timezone);
      }

      logger.info('Timezone updated successfully', {
        component: 'TimezoneSelector',
        old_timezone: user?.timezone,
        new_timezone: updatedUser.timezone,
      });
    },
    onError: error => {
      toast.error(t('settings.timezone.update_error'));
      logger.error('Failed to update timezone', error, { component: 'TimezoneSelector' });
    },
  });

  const handleTimezoneChange = async (timezone: string) => {
    if (!user?.id) {
      logger.warn('Cannot update timezone: no user ID', { component: 'TimezoneSelector' });
      return;
    }

    // Don't update if already the same timezone
    const currentTz = selectedTimezone || user.timezone;
    if (timezone === currentTz) {
      logger.info('Timezone already set to this value', {
        component: 'TimezoneSelector',
        timezone,
        currentTz,
      });
      return;
    }

    logger.info('Updating timezone', {
      component: 'TimezoneSelector',
      userId: user.id,
      oldTimezone: user.timezone,
      newTimezone: timezone,
    });

    setSelectedTimezone(timezone);
    await updateTimezone(`/users/${user.id}`, { timezone });
  };

  // Filter timezones based on search query
  const filteredTimezones = useMemo(() => {
    if (!searchQuery.trim()) return timezones;

    const query = searchQuery.toLowerCase();
    const filtered: Record<string, string[]> = {};

    Object.entries(timezones).forEach(([region, tzList]) => {
      const matchingTz = tzList.filter(
        tz =>
          tz.toLowerCase().includes(query) ||
          formatTimezoneDisplay(tz).toLowerCase().includes(query)
      );

      if (matchingTz.length > 0) {
        filtered[region] = matchingTz;
      }
    });

    return filtered;
  }, [timezones, searchQuery]);

  if (!user) return null;

  // Default to Europe/Paris if no timezone set
  const currentTimezone = selectedTimezone || user.timezone || 'Europe/Paris';
  const isBrowserDetected = browserTimezone === currentTimezone;

  const content = (
    <div className="space-y-4">
      {!mounted ? (
        <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
      ) : (
        <>
          {/* Current timezone display */}
          {currentTimezone && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-2">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 space-y-1">
                  <Label className="text-sm font-medium">{t('settings.timezone.current')}</Label>
                  <p className="text-base font-semibold text-primary">
                    {formatTimezoneDisplay(currentTimezone)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {getCurrentTimeInTimezone(currentTimezone, lng === 'fr' ? 'fr-FR' : 'en-US')}
                  </p>
                </div>
                {isBrowserDetected && (
                  <div className="rounded-md bg-green-500/10 px-2 py-1 text-xs text-green-700 dark:text-green-400">
                    {t('settings.timezone.browser_match')}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Browser timezone suggestion */}
          {browserTimezone && browserTimezone !== currentTimezone && (
            <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3 space-y-2">
              <div className="flex items-start gap-2">
                <Info className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
                <div className="flex-1 space-y-2">
                  <p className="text-sm text-blue-900 dark:text-blue-100">
                    {t('settings.timezone.browser_suggestion')}
                  </p>
                  <button
                    type="button"
                    onClick={() => handleTimezoneChange(browserTimezone)}
                    disabled={updating}
                    className="text-sm font-medium text-blue-700 dark:text-blue-300 hover:underline disabled:opacity-50"
                  >
                    {t('settings.timezone.use_browser')} ({formatTimezoneDisplay(browserTimezone)})
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Search input */}
          <div className="space-y-2">
            <Label htmlFor="timezone-search">{t('settings.timezone.search_label')}</Label>
            <Input
              id="timezone-search"
              type="text"
              placeholder={t('settings.timezone.search_placeholder')}
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full"
            />
          </div>

          {/* Timezone list */}
          <div className="space-y-4 max-h-96 overflow-y-auto pr-2">
            {Object.entries(filteredTimezones).length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                {t('settings.timezone.no_results')}
              </p>
            ) : (
              Object.entries(filteredTimezones).map(([region, tzList]) => (
                <div key={region} className="space-y-2">
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                    {region}
                  </h3>
                  <div className="grid gap-2">
                    {tzList.map(timezone => {
                      const isSelected = timezone === currentTimezone;
                      const displayName = formatTimezoneDisplay(timezone);

                      return (
                        <button
                          key={timezone}
                          type="button"
                          onClick={() => handleTimezoneChange(timezone)}
                          disabled={updating || isSelected}
                          className={`
                            relative flex items-start gap-3 rounded-lg border-2 p-3 text-left transition-all
                            hover:bg-accent hover:shadow-sm
                            disabled:opacity-50 disabled:cursor-not-allowed
                            ${
                              isSelected
                                ? 'border-primary bg-primary/5 shadow-sm'
                                : 'border-border bg-card'
                            }
                          `}
                          aria-label={`Select ${displayName}`}
                        >
                          {/* Selection indicator */}
                          <div
                            className={`
                              mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors
                              ${
                                isSelected
                                  ? 'border-primary bg-primary text-primary-foreground'
                                  : 'border-muted-foreground/30'
                              }
                            `}
                          >
                            {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
                          </div>

                          {/* Timezone details */}
                          <div className="flex-1 space-y-0.5">
                            <Label
                              className={`cursor-pointer text-sm font-medium ${
                                isSelected ? 'text-primary' : 'text-foreground'
                              }`}
                            >
                              {displayName}
                            </Label>
                            <p className="text-xs text-muted-foreground">{timezone}</p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Info note */}
          <InfoBox>
            <p className="text-xs text-muted-foreground">{t('settings.timezone.info_note')}</p>
          </InfoBox>
        </>
      )}
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="timezone"
      title={t('settings.timezone.title')}
      description={t('settings.timezone.description')}
      icon={Globe}
    >
      {content}
    </SettingsSection>
  );
}
