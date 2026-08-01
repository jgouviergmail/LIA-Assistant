'use client';

/**
 * RelationCardList — the CRM overview (N-09, restyled with favorites).
 *
 * Two distinct bands — « Favoris » then everyone else — so a long address
 * book stays scannable; each card carries an initials avatar (stable tint),
 * colored signal pills instead of gray text, an optional peers badge, and a
 * star that toggles WITHOUT opening the card. The star is a SIBLING button
 * overlaid on the card (a button inside a button is invalid HTML and a
 * keyboard trap).
 *
 * Past a dozen people a toolbar appears — name search, ordering, and two
 * quick filters. All of it is client-side over rows already fetched: an
 * ordering preference is not worth a server round-trip, and the server's own
 * ranking stays the default so the page opens on what matters most.
 *
 * A relationship that has been silent for a quarter carries a discreet
 * "dormant" chip: a prompt to act, never a verdict on the person.
 */

import { useState } from 'react';
import {
  Handshake,
  ListTodo,
  MessageSquare,
  Moon,
  PhoneCall,
  Search,
  Star,
  Users,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import { timeAgoLabel } from '@/lib/briefing-utils';
import { RelationAvatar } from '@/components/relations/RelationAvatar';
import type { RelationSummary } from '@/hooks/useRelations';

/** Show the toolbar once the list stops fitting one glance. */
const FILTER_THRESHOLD = 9;

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
      <button
        type="button"
        onClick={() => onOpen(relation.display_name)}
        className="w-full rounded-xl border border-border/50 bg-card p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <div className="flex items-center gap-3">
          <RelationAvatar name={relation.display_name} />
          <div className="min-w-0 flex-1 pr-10">
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
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] text-muted-foreground">
                  {timeAgoLabel(t, relation.last_interaction_at)}
                </span>
                {isDormant(relation) && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full border border-border/60 bg-muted/60 px-1.5 py-px text-[9px] font-medium text-muted-foreground"
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
              <span className="text-[11px] italic text-muted-foreground">
                {t('relations.no_recent_signal')}
              </span>
            )}
          </div>
        </div>
        {(relation.open_loops_count > 0 ||
          relation.calls_count > 0 ||
          relation.peer_messages_count > 0) && (
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
            {/* amber-800, not -700: at 11px on the tinted background the -700
                pair measures 4.34:1, under the 4.5:1 AA floor (axe, production
                bundle). Same fix as the v1.27.0 pills. */}
            {relation.open_loops_count > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 font-medium text-amber-800 dark:text-amber-300">
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
            {/* Primary tint: everything relayed through LIA shares the peers
                identity colour (the "LIA" badge above, the chat bubbles). */}
            {relation.peer_messages_count > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 font-medium text-primary">
                <MessageSquare className="h-3 w-3" aria-hidden="true" />
                {t('relations.peer_messages_count', { count: relation.peer_messages_count })}
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

/** A toggle chip — a real button with `aria-pressed`, never a styled div. */
function FilterChip({
  active,
  label,
  icon: Icon,
  onToggle,
}: {
  active: boolean;
  label: string;
  icon: typeof Users;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active
          ? 'border-primary/40 bg-primary/10 text-primary'
          : 'border-border/60 text-muted-foreground hover:bg-muted/60'
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </button>
  );
}

/**
 * Name search, ordering and quick filters — all client-side.
 *
 * Native `<select>` on purpose: a Radix Select is untestable in jsdom, and the
 * codebase already made that call for the peers calendar level.
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
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative w-full max-w-xs sm:w-auto sm:flex-1">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          value={filter}
          onChange={event => onFilter(event.target.value)}
          placeholder={t('relations.filter_placeholder')}
          aria-label={t('relations.filter_placeholder')}
          className="h-11 w-full rounded-full border border-border bg-background pl-8 pr-3 text-base focus:outline-none focus:ring-1 focus:ring-ring sm:h-9 sm:text-sm"
        />
      </div>
      <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {t('relations.sort_label')}
        <select
          value={sort}
          onChange={event => onSort(event.target.value as SortMode)}
          className="h-9 rounded-lg border border-border bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="recent">{t('relations.sort_recent')}</option>
          <option value="name">{t('relations.sort_name')}</option>
          <option value="volume">{t('relations.sort_volume')}</option>
        </select>
      </label>
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
    </div>
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

  if (relations.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center">
        <Users className="h-8 w-8 text-muted-foreground/50" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">{t('relations.empty')}</p>
      </div>
    );
  }

  const needle = filter.trim().toLowerCase();
  const matching = relations.filter(
    relation =>
      (!needle || relation.display_name.toLowerCase().includes(needle)) &&
      (!onlyPeers || relation.is_peer) &&
      (!onlyDormant || isDormant(relation))
  );
  const visible = sortRelations(matching, sort);
  const favorites = visible.filter(relation => relation.is_favorite);
  const others = visible.filter(relation => !relation.is_favorite);

  return (
    <div className="space-y-7">
      {relations.length >= FILTER_THRESHOLD && (
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

      {/* The list is a page too: past the server cap people would simply
          vanish, so what it left out is stated rather than applied in
          silence (ADR-185). Counted against the WHOLE list, never against
          the client-side filter — which the user chose and can undo. */}
      {typeof relationsTotal === 'number' && relationsTotal > relations.length && (
        <p className="text-center text-xs text-muted-foreground">
          {t('relations.more_not_shown', { count: relationsTotal - relations.length })}
        </p>
      )}
    </div>
  );
}
