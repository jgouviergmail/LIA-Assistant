'use client';

/**
 * RelationCardList — the CRM overview (N-09, restyled with favorites).
 *
 * Two distinct bands — « Favoris » then everyone else — so a long address
 * book stays scannable; each card carries an initials avatar (stable tint),
 * its name on one line, signal pills in one tone at its foot (an optional
 * peers badge among them), and a
 * star that toggles WITHOUT opening the card. The star is a SIBLING button
 * overlaid on the card (a button inside a button is invalid HTML and a
 * keyboard trap).
 *
 * The toolbar stays visible — name search, ordering, and two quick filters.
 * All of it is client-side over rows already fetched: an
 * ordering preference is not worth a server round-trip, and the server's own
 * ranking stays the default so the page opens on what matters most.
 *
 * A relationship that has been silent for a quarter carries a discreet
 * "dormant" chip: a prompt to act, never a verdict on the person.
 */

import { useState } from 'react';
import { RelationActivityBadges } from './RelationActivityBadges';
import { Handshake, Moon, Star, Users } from '@/lib/icons';
import { useTranslation } from 'react-i18next';

import { cn, normalizeSearchText } from '@/lib/utils';
import { timeAgoLabel } from '@/lib/briefing-utils';
import { RelationAvatar } from '@/components/relations/RelationAvatar';
import type { RelationSummary } from '@/hooks/useRelations';
import { EmptyState } from '@/components/ui/empty-state';
import { HeadingRule } from '@/components/ui/heading-rule';
import { FilterChip } from '@/components/ui/filter-chip';
import { ListToolbar } from '@/components/ui/list-toolbar';

/** Past this silence, a relationship is worth noticing again. */
const DORMANT_AFTER_DAYS = 90;

type SortMode = 'recent' | 'name' | 'volume';

/** Whether a relationship has gone quiet — a prompt to act, not a verdict. */
function isDormant(relation: RelationSummary, now: number = Date.now()): boolean {
  if (!relation.last_interaction_at) return false;
  const elapsed = now - new Date(relation.last_interaction_at).getTime();
  return elapsed > DORMANT_AFTER_DAYS * 24 * 60 * 60 * 1000;
}

function signalCount(relation: RelationSummary): number {
  return relation.open_loops_count + relation.calls_count + relation.peer_messages_count;
}

/**
 * Order the list without touching the bands.
 *
 * `recent` keeps the server's ranking (it already resolved recency and put
 * favorites first); the other modes are pure client re-orderings of the same
 * rows — no refetch, no server round-trip for a display preference.
 */
function sortRelations(relations: RelationSummary[], mode: SortMode): RelationSummary[] {
  if (mode === 'recent') return relations;
  const sorted = [...relations];
  if (mode === 'name') {
    sorted.sort((a, b) => a.display_name.localeCompare(b.display_name));
  } else {
    sorted.sort(
      (a, b) => signalCount(b) - signalCount(a) || a.display_name.localeCompare(b.display_name)
    );
  }
  return sorted;
}

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
      {/* A column: the person on top, the counts at its foot on the right
          (owner request 2026-10-21), whatever the neighbour cards hold. */}
      <button
        type="button"
        onClick={() => onOpen(relation.display_name)}
        className="flex h-full w-full flex-col gap-3 rounded-xl border border-border bg-card p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {/* The right gutter keeps the name clear of the overlaid star. */}
        <div className="flex w-full min-w-0 items-center gap-3 pr-10">
          <RelationAvatar name={relation.display_name} />
          <div className="min-w-0 flex-1">
            {/* One line, always: a long name is cut, and stated whole on hover. */}
            <span
              className="block truncate font-semibold text-foreground"
              title={relation.display_name}
            >
              {relation.display_name}
            </span>
            {relation.last_interaction_at ? (
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="text-px-11 text-muted-foreground">
                  {timeAgoLabel(t, relation.last_interaction_at)}
                </span>
                {isDormant(relation) && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full border border-border/60 bg-muted/60 px-1.5 py-px text-px-9 font-medium text-muted-foreground"
                    title={t('relations.dormant_hint')}
                  >
                    <Moon className="h-2.5 w-2.5" aria-hidden="true" />
                    {t('relations.dormant')}
                  </span>
                )}
              </span>
            ) : (
              // Full muted-foreground: a diluted italic falls under the AA
              // contrast floor at this size (same defect as the detail panel).
              <span className="text-px-11 italic text-muted-foreground">
                {t('relations.no_recent_signal')}
              </span>
            )}
          </div>
        </div>
        <RelationActivityBadges relation={relation} />
      </button>
      {/* Sibling star, overlaid — toggles without opening the card. */}
      <button
        type="button"
        onClick={() => onToggleFavorite(relation.display_name, !relation.is_favorite)}
        aria-label={starLabel}
        aria-pressed={relation.is_favorite}
        className="absolute right-1 top-1 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
      {/* A rubrique heading draws the same hairline on every screen (owner
          request 2026-10-21) — the settings groups', the timelines'. */}
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        {title}
        <span className="rounded-full bg-muted px-2 py-px text-px-11 font-medium tabular-nums text-muted-foreground">
          {count}
        </span>
        <HeadingRule />
      </h2>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" role="list">
        {children}
      </ul>
    </section>
  );
}

/**
 * Name search, ordering and quick filters — all client-side.
 *
 * The shared toolbar keeps the same search, native choices and chip layout
 * as the other dashboard lists.
 */
function Toolbar({
  filter,
  onFilter,
  sort,
  onSort,
  onlyPeers,
  onTogglePeers,
  onlyDormant,
  onToggleDormant,
}: {
  filter: string;
  onFilter: (value: string) => void;
  sort: SortMode;
  onSort: (value: SortMode) => void;
  onlyPeers: boolean;
  onTogglePeers: () => void;
  onlyDormant: boolean;
  onToggleDormant: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ListToolbar<SortMode>
      query={filter}
      onQuery={onFilter}
      searchLabel={t('relations.filter_placeholder')}
      sort={sort}
      onSort={onSort}
      sortLabel={t('relations.sort_label')}
      sortOptions={(['recent', 'name', 'volume'] as const).map(value => ({
        value,
        label: t(`relations.sort_${value}`),
      }))}
      chips={
        <>
          <FilterChip
            active={onlyPeers}
            label={t('relations.only_peers')}
            icon={Handshake}
            onToggle={onTogglePeers}
          />
          <FilterChip
            active={onlyDormant}
            label={t('relations.only_dormant')}
            icon={Moon}
            onToggle={onToggleDormant}
          />
        </>
      }
    />
  );
}

export function RelationCardList({
  relations,
  relationsTotal,
  onOpen,
  onToggleFavorite,
}: {
  relations: RelationSummary[];
  /** Exact number found server-side, before the page cap (ADR-185). */
  relationsTotal?: number;
  onOpen: (name: string) => void;
  onToggleFavorite: (name: string, nextValue: boolean) => void;
}) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState<SortMode>('recent');
  const [onlyPeers, setOnlyPeers] = useState(false);
  const [onlyDormant, setOnlyDormant] = useState(false);

  const hasFilter = Boolean(filter || onlyPeers || onlyDormant);
  const resetFilters = () => {
    setFilter('');
    setOnlyPeers(false);
    setOnlyDormant(false);
  };
  const needle = normalizeSearchText(filter.trim());
  const matching = relations.filter(
    relation =>
      (!needle || normalizeSearchText(relation.display_name).includes(needle)) &&
      (!onlyPeers || relation.is_peer) &&
      (!onlyDormant || isDormant(relation))
  );
  const visible = sortRelations(matching, sort);
  const favorites = visible.filter(relation => relation.is_favorite);
  const others = visible.filter(relation => !relation.is_favorite);

  return (
    <div className="space-y-7">
      <Toolbar
        filter={filter}
        onFilter={setFilter}
        sort={sort}
        onSort={setSort}
        onlyPeers={onlyPeers}
        onTogglePeers={() => setOnlyPeers(value => !value)}
        onlyDormant={onlyDormant}
        onToggleDormant={() => setOnlyDormant(value => !value)}
      />

      {typeof relationsTotal === 'number' && relationsTotal > relations.length && (
        <p className="text-xs text-muted-foreground">
          {t('relations.more_not_shown', { count: relationsTotal - relations.length })}
        </p>
      )}

      {relations.length === 0 && !hasFilter ? (
        <EmptyState icon={Users} description={t('relations.empty')} />
      ) : visible.length === 0 ? (
        <EmptyState
          reason="no-match"
          description={t('relations.filter_no_match')}
          action={{ label: t('relations.clear_filters'), onClick: resetFilters }}
        />
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
              title={favorites.length > 0 ? t('relations.others_title') : t('relations.all_title')}
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
