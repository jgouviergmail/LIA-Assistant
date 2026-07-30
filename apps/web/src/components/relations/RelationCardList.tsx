'use client';

/**
 * RelationCardList — the CRM overview (N-09, restyled with favorites).
 *
 * Two distinct bands — « Favoris » then everyone else — so a long address
 * book stays scannable; each card carries an initials avatar (stable tint),
 * colored signal pills instead of gray text, an optional peers badge, and a
 * star that toggles WITHOUT opening the card. The star is a SIBLING button
 * overlaid on the card (a button inside a button is invalid HTML and a
 * keyboard trap). Past a dozen people a name filter appears.
 */

import { useState } from 'react';
import { Handshake, ListTodo, PhoneCall, Search, Star, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { timeAgoLabel } from '@/lib/briefing-utils';
import { RelationAvatar } from '@/components/relations/RelationAvatar';
import type { RelationSummary } from '@/hooks/useRelations';

/** Show the name filter once the list stops fitting one glance. */
const FILTER_THRESHOLD = 9;

function RelationCard({
  relation,
  onOpen,
  onToggleFavorite,
}: {
  relation: RelationSummary;
  onOpen: (name: string) => void;
  onToggleFavorite: (name: string, nextValue: boolean) => void;
}) {
  const { t } = useTranslation();
  const starLabel = relation.is_favorite
    ? t('relations.favorite_remove', { name: relation.display_name })
    : t('relations.favorite_add', { name: relation.display_name });

  return (
    <li className="relative">
      <button
        type="button"
        onClick={() => onOpen(relation.display_name)}
        className="w-full rounded-xl border border-border/50 bg-card p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="flex items-center gap-3">
          <RelationAvatar name={relation.display_name} />
          <div className="min-w-0 flex-1 pr-7">
            <span className="flex items-center gap-1.5">
              <span className="truncate font-semibold text-foreground">
                {relation.display_name}
              </span>
              {relation.is_peer && (
                <span
                  className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-primary/25 bg-primary/10 px-1.5 py-px text-[9px] font-semibold text-primary"
                  title={t('relations.peer_badge_hint')}
                >
                  <Handshake className="h-2.5 w-2.5" aria-hidden="true" />
                  LIA
                </span>
              )}
            </span>
            {relation.last_interaction_at ? (
              <span className="text-[11px] text-muted-foreground">
                {timeAgoLabel(t, relation.last_interaction_at)}
              </span>
            ) : (
              <span className="text-[11px] italic text-muted-foreground/70">
                {t('relations.no_recent_signal')}
              </span>
            )}
          </div>
        </div>
        {(relation.open_loops_count > 0 || relation.calls_count > 0) && (
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            {relation.open_loops_count > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 font-medium text-amber-700 dark:text-amber-300">
                <ListTodo className="h-3 w-3" aria-hidden="true" />
                {t('relations.open_loops_count', { count: relation.open_loops_count })}
              </span>
            )}
            {relation.calls_count > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-sky-500/25 bg-sky-500/10 px-2 py-0.5 font-medium text-sky-700 dark:text-sky-300">
                <PhoneCall className="h-3 w-3" aria-hidden="true" />
                {t('relations.calls_count', { count: relation.calls_count })}
              </span>
            )}
          </div>
        )}
      </button>
      {/* Sibling star, overlaid — toggles without opening the card. */}
      <button
        type="button"
        onClick={() => onToggleFavorite(relation.display_name, !relation.is_favorite)}
        aria-label={starLabel}
        aria-pressed={relation.is_favorite}
        className="absolute right-2.5 top-2.5 rounded-full p-1.5 transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Star
          aria-hidden="true"
          className={cn(
            'h-4 w-4 transition-colors',
            relation.is_favorite
              ? 'fill-amber-400 text-amber-400'
              : 'text-muted-foreground/50 hover:text-muted-foreground'
          )}
        />
      </button>
    </li>
  );
}

function Band({
  icon: Icon,
  title,
  count,
  children,
}: {
  icon: typeof Star;
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        {title}
        <span className="rounded-full bg-muted px-2 py-px text-[11px] font-medium tabular-nums text-muted-foreground">
          {count}
        </span>
      </h2>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" role="list">
        {children}
      </ul>
    </section>
  );
}

export function RelationCardList({
  relations,
  onOpen,
  onToggleFavorite,
}: {
  relations: RelationSummary[];
  onOpen: (name: string) => void;
  onToggleFavorite: (name: string, nextValue: boolean) => void;
}) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState('');

  if (relations.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center">
        <Users className="h-8 w-8 text-muted-foreground/50" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">{t('relations.empty')}</p>
      </div>
    );
  }

  const needle = filter.trim().toLowerCase();
  const visible = needle
    ? relations.filter(relation => relation.display_name.toLowerCase().includes(needle))
    : relations;
  const favorites = visible.filter(relation => relation.is_favorite);
  const others = visible.filter(relation => !relation.is_favorite);

  return (
    <div className="space-y-7">
      {relations.length >= FILTER_THRESHOLD && (
        <div className="relative max-w-xs">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            type="search"
            value={filter}
            onChange={event => setFilter(event.target.value)}
            placeholder={t('relations.filter_placeholder')}
            aria-label={t('relations.filter_placeholder')}
            className="h-9 w-full rounded-full border border-border bg-background pl-8 pr-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      )}

      {visible.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {t('relations.filter_no_match')}
        </p>
      ) : (
        <>
          {favorites.length > 0 && (
            <Band icon={Star} title={t('relations.favorites_title')} count={favorites.length}>
              {favorites.map(relation => (
                <RelationCard
                  key={relation.display_name}
                  relation={relation}
                  onOpen={onOpen}
                  onToggleFavorite={onToggleFavorite}
                />
              ))}
            </Band>
          )}
          {others.length > 0 && (
            <Band
              icon={Users}
              title={
                favorites.length > 0 ? t('relations.others_title') : t('relations.all_title')
              }
              count={others.length}
            >
              {others.map(relation => (
                <RelationCard
                  key={relation.display_name}
                  relation={relation}
                  onOpen={onOpen}
                  onToggleFavorite={onToggleFavorite}
                />
              ))}
            </Band>
          )}
        </>
      )}
    </div>
  );
}
