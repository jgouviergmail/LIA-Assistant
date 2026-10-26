'use client';

import { useState } from 'react';
import { ArrowUpRight, BookOpen, Bot, Globe, Search } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { SettingsSearchAvailability } from '@/lib/settings-search';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import { visibleDestinations, destinationPath } from '@/lib/dashboard-nav';
import { useAppConfig } from '@/hooks/useAppConfig';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { normalizeSearchText } from '@/lib/utils';
import { WORLD } from './definition';
import {
  searchWorldCatalogue,
  worldActions,
  functionSurface,
  type FunctionSurface,
  type FunctionPlace,
} from './functions';
import type { ZoneId } from './types';

export function WorldCatalogue({
  lng,
  availability,
  place,
  onSelect,
  onCompose,
  surface = 'activity',
}: {
  surface?: FunctionSurface;
  lng: Language;
  availability: SettingsSearchAvailability;
  place: ZoneId | null;
  onSelect(token: SettingsSectionToken): void;
  onCompose(draft: string): void;
}) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const [query, setQuery] = useState('');
  const catalogue = searchWorldCatalogue(availability, t, query).filter(
    item => functionSurface(item.token) === surface && (!place || item.place === place)
  );
  const needle = normalizeSearchText(query);
  const actions = worldActions(t).filter(
    item =>
      surface === 'activity' &&
      (!place || item.place === place) &&
      (!needle || normalizeSearchText(item.label + ' ' + item.description).includes(needle))
  );
  const groups: FunctionPlace[] = place
    ? [place]
    : [...WORLD.zones.map(zone => zone.id), 'transverse'];
  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="relative shrink-0">
        <Search
          className="pointer-events-none absolute left-3 top-3.5 size-4 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          type="search"
          className="h-11 pl-9"
          value={query}
          onChange={event => setQuery(event.target.value)}
          aria-label={t('world.functions.search')}
          placeholder={t('world.functions.search')}
        />
      </div>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pb-4 pr-1">
        {groups.map(group => {
          const settings = catalogue.filter(item => item.place === group);
          const commands = actions.filter(item => item.place === group);
          if (!settings.length && !commands.length) return null;
          return (
            <section key={group} className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <BookOpen className="size-4 text-primary" aria-hidden="true" />
                {t(group === 'transverse' ? 'world.functions.transverse' : 'world.zones.' + group)}
              </h3>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {commands.map(command => (
                  <Button
                    key={command.id}
                    variant="outline"
                    className="h-auto min-h-20 items-start justify-start gap-3 whitespace-normal p-3 text-left"
                    onClick={() => {
                      if (command.insertText) onCompose(command.insertText);
                    }}
                  >
                    <Bot className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden="true" />
                    <span>
                      <span className="block text-sm">{command.label}</span>
                      <span className="mt-1 block text-xs font-normal leading-relaxed text-foreground/80">
                        {command.description}
                      </span>
                    </span>
                  </Button>
                ))}
                {settings.map(item => (
                  <Button
                    key={item.token}
                    variant="outline"
                    className="h-auto min-h-16 justify-start whitespace-normal p-3 text-left"
                    onClick={() => onSelect(item.token)}
                  >
                    {t(item.titleKey)}
                  </Button>
                ))}
              </div>
            </section>
          );
        })}
        {!catalogue.length && !actions.length && (
          <p role="status" className="text-sm text-foreground/80">
            {t('world.functions.empty')}
          </p>
        )}
        {surface === 'activity' && !place && !query.trim() && (
          <section className="space-y-3 border-t border-border pt-4">
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Globe className="size-4 text-primary" aria-hidden="true" />
              {t('world.functions.application')}
            </h3>
            <div className="flex flex-wrap gap-2">
              {visibleDestinations(config?.features)
                .filter(item => !['world', 'settings', 'chat'].includes(item.segment))
                .map(item => (
                  <Button key={item.segment} variant="outline" className="min-h-11" asChild>
                    <Link href={buildLocalizedPath(destinationPath(item.segment), lng)}>
                      {t(item.labelKey)}
                      <ArrowUpRight className="size-4" aria-hidden="true" />
                    </Link>
                  </Button>
                ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
