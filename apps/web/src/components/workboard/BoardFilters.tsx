'use client';
/**
 * What the board is narrowed to (ADR-276).
 *
 * The same glyph lists the cards and the panel carry (D81): a filter's items
 * wear the marks of what they narrow to — a person, a ranked priority, a
 * sort key — and « any » wears ONE sign wherever it appears. Every control
 * is labelled with its family's glyph, and the search box is debounced by
 * the caller's own state rather than firing a request per keystroke.
 *
 * **On a phone the block FOLDS** (owner, 2026-09-10). Five controls above one
 * column of cards is a wall, and the reader came to look at their tickets, not
 * at the controls. Folded it becomes an index entry, so it says WHAT it holds
 * before being opened — the exact count of active narrowings and their own
 * words (`lib/workboard/active-filters.ts`) — which is the whole point of the
 * fold: a summary that says nothing makes the reader open it to find out.
 *
 * Closed means UNMOUNTED (`components/ui/disclosure.tsx` uses a native
 * `<details>` and renders its children only while open), and the filter state
 * lives in the PAGE, so folding costs nothing and loses nothing. Above `lg`
 * the block is unchanged: a full-width row of four fields, always visible.
 *
 * **The lane filter exists only on a board that has lanes.** A reader with no
 * category in sight has nothing to narrow to, and a list offering « all » and
 * « to categorize » alone would describe a board they do not have.
 */
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Filter, X } from '@/lib/icons';

import { Button } from '@/components/ui/button';
import { Disclosure } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { GlyphLabel, GlyphSelect } from '@/components/workboard/GlyphSelect';
import { PRIORITY_ANY, PrioritySelect } from '@/components/workboard/PrioritySelect';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { activeFilterCount, describeFilters } from '@/lib/workboard/active-filters';
import { SEARCH_MAX_CHARS } from '@/lib/workboard/filters-url';
import { anyIcon, filterIcon, laneIcon, partyIcon, sortIcon } from '@/lib/workboard/icons';
import { UNFILED_LANE } from '@/lib/workboard/lanes';
import type { BoardFilters as Filters, BoardSide, BoardSort } from '@/types/workboard';

const SIDES: readonly BoardSide[] = ['all', 'me', 'lia', 'peer'];
const SORTS: readonly BoardSort[] = ['position', 'priority', 'due', 'updated', 'created'];

/** The list's value for « every lane » — never a category id, which is a UUID. */
const LANE_ANY = 'any';

/** One lane the board can be narrowed to. */
export interface LaneOption {
  /** The category. */
  id: string;
  /** How the list names it — its name, and whose it is when not the reader's. */
  name: string;
}

export interface BoardFiltersProps {
  lng: Language;
  filters: Filters;
  onChange: (filters: Filters) => void;
  /**
   * The categories on the reader's board, theirs and those of the tickets
   * they hold. Empty or absent, the lane filter is not drawn.
   */
  lanes?: readonly LaneOption[];
  /**
   * Fold the block behind a summary. The page passes `true` below `lg`, where
   * one column of cards shows at a time and the controls would otherwise take
   * the whole first screen.
   */
  collapsible?: boolean;
}

/** The family glyph in a label, and the glyph on each item. */
const LABEL_GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';
const ITEM_GLYPH = 'h-3.5 w-3.5 shrink-0';
const ANY_GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';
const FIELD = 'h-10 px-3 text-sm';

/**
 * What the lane list shows for the filters in force.
 *
 * The list picks ONE lane; a link may carry several. It then shows the first
 * it can name — and « all » for a lane the board no longer carries, rather
 * than a list with no selected value.
 */
function laneValue(filters: Filters, lanes: readonly LaneOption[]): string {
  const chosen = filters.category?.find(id => lanes.some(lane => lane.id === id));
  if (chosen !== undefined) return chosen;
  return filters.uncategorized ? UNFILED_LANE : LANE_ANY;
}

export function BoardFilters({
  filters,
  onChange,
  lanes = [],
  collapsible = false,
}: BoardFiltersProps) {
  const { t } = useTranslation();
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const reset = () => onChange({ assignee: 'all', sort: 'position' });

  const clearButton = (
    <Button variant="outline" size="sm" onClick={reset}>
      <X className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
      {t('workboard.filters.reset')}
    </Button>
  );

  const controls = (
    <>
      {/* A GRID, never a wrapping row of fixed widths: those left one field
          alone on its line at some widths and three on others, so nothing
          lined up with anything. One column on a phone, two from `sm`, four
          from `xl` — the fields share the width and their labels sit on the
          same baselines. */}
      <div
        className={cn(
          'grid gap-3 sm:grid-cols-2',
          lanes.length > 0 ? 'xl:grid-cols-5' : 'xl:grid-cols-4'
        )}
      >
        <div className="space-y-2">
          <GlyphLabel htmlFor="wb-q" glyph={filterIcon('search', LABEL_GLYPH)}>
            {t('workboard.filters.search')}
          </GlyphLabel>
          {/* The API's own bound, published to the field that produces the
              value (ADR-184): past it the request is refused, and a board
              showing a generic failure for a search too long is a bug the
              person cannot act on. */}
          <Input
            id="wb-q"
            value={filters.q ?? ''}
            maxLength={SEARCH_MAX_CHARS}
            placeholder={t('workboard.filters.search')}
            onChange={event => set({ q: event.target.value })}
          />
        </div>

        <div className="space-y-2">
          {/* Who holds it: the badge's own marks, « everyone » the « any » sign. */}
          <GlyphSelect
            id="wb-side"
            hideLabel={false}
            label={t('workboard.filters.side')}
            labelGlyph={filterIcon('side', LABEL_GLYPH)}
            value={filters.assignee ?? 'all'}
            className={FIELD}
            items={SIDES.map(side => ({
              value: side,
              glyph: side === 'all' ? anyIcon(ANY_GLYPH) : partyIcon(side, ITEM_GLYPH),
              text: t(`workboard.filters.side_${side}`),
            }))}
            onChange={chosen => {
              const assignee = SIDES.find(side => side === chosen);
              if (assignee) set({ assignee });
            }}
          />
        </div>

        {lanes.length > 0 && (
          <div className="space-y-2">
            {/* Which lane: « all », what is not filed yet, or one category.
                `undefined` for an unset half, never `[]` or `false`. */}
            <GlyphSelect
              id="wb-lane"
              hideLabel={false}
              label={t('workboard.filters.category')}
              labelGlyph={filterIcon('category', LABEL_GLYPH)}
              value={laneValue(filters, lanes)}
              className={FIELD}
              items={[
                {
                  value: LANE_ANY,
                  glyph: anyIcon(ANY_GLYPH),
                  text: t('workboard.filters.category_any'),
                },
                {
                  value: UNFILED_LANE,
                  glyph: laneIcon(false, ANY_GLYPH),
                  text: t('workboard.lanes.unfiled'),
                },
                ...lanes.map(lane => ({
                  value: lane.id,
                  glyph: laneIcon(true, ANY_GLYPH),
                  text: lane.name,
                })),
              ]}
              onChange={chosen =>
                set({
                  category: lanes.some(lane => lane.id === chosen) ? [chosen] : undefined,
                  uncategorized: chosen === UNFILED_LANE ? true : undefined,
                })
              }
            />
          </div>
        )}

        <div className="space-y-2">
          {/* `undefined`, never `[]` or `''`: an unset filter must cost no query
              parameter, so the server keeps its own default. */}
          <PrioritySelect
            id="wb-priority-filter"
            withAny
            hideLabel={false}
            label={t('workboard.filters.priority')}
            labelGlyph={filterIcon('priority', LABEL_GLYPH)}
            value={filters.priority?.[0] ?? PRIORITY_ANY}
            className={FIELD}
            onChange={priority =>
              set({ priority: priority === PRIORITY_ANY ? undefined : [priority] })
            }
          />
        </div>

        <div className="space-y-2">
          <GlyphSelect
            id="wb-sort"
            hideLabel={false}
            label={t('workboard.filters.sort')}
            labelGlyph={filterIcon('sort', LABEL_GLYPH)}
            value={filters.sort ?? 'position'}
            className={FIELD}
            items={SORTS.map(sort => ({
              value: sort,
              glyph: sortIcon(sort, ANY_GLYPH),
              text: t(`workboard.filters.sort_${sort}`),
            }))}
            onChange={chosen => {
              const sort = SORTS.find(candidate => candidate === chosen);
              if (sort) set({ sort });
            }}
          />
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        {/* `aria-label` beside the visible `<Label htmlFor>`, both saying the
            same sentence: `jsx-a11y` cannot follow `htmlFor` → `id` across two
            components (measured 2026-08-05, 96 findings on correct code), so
            the name has to be readable on the control itself. */}
        <input
          id="wb-overdue"
          type="checkbox"
          aria-label={t('workboard.filters.overdue')}
          className="h-4 w-4 rounded border-input"
          checked={Boolean(filters.overdue)}
          onChange={event => set({ overdue: event.target.checked || undefined })}
        />
        <Label htmlFor="wb-overdue" className="text-sm">
          {t('workboard.filters.overdue')}
        </Label>
      </div>
    </>
  );

  if (collapsible)
    return (
      <FoldedFilters filters={filters} lanes={lanes}>
        {controls}
        {clearButton}
      </FoldedFilters>
    );

  return (
    <section
      aria-label={t('workboard.filters.title')}
      className="rounded-xl border border-border bg-card p-3"
    >
      {/* A title always carries an icon, in the theme colour. « Clear »
          belongs on the title's own line: at the end of a wrapping row of
          controls it landed wherever the last field happened to stop. */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Filter className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('workboard.filters.title')}
        </h2>
        {clearButton}
      </div>
      {controls}
    </section>
  );
}

/**
 * The phone shape: a summary that says what is narrowed, and the controls under it.
 *
 * The badge is the EXACT number of active narrowings and the description their
 * own words — a fold whose summary says nothing is a fold the reader opens to
 * find out. Both come from `lib/workboard/active-filters.ts`, which the empty
 * state reads too, so the board cannot say « no match » while the summary says
 * nothing is filtered.
 */
function FoldedFilters({
  filters,
  lanes,
  children,
}: {
  filters: Filters;
  lanes: readonly LaneOption[];
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const count = activeFilterCount(filters);
  const described = describeFilters(
    filters,
    t,
    categoryId => lanes.find(lane => lane.id === categoryId)?.name
  );
  return (
    <Disclosure
      icon={Filter}
      title={t('workboard.filters.title')}
      badge={count > 0 ? count : undefined}
      badgeClassName={count > 0 ? 'bg-primary/15 text-primary' : undefined}
      description={described || t('workboard.filters.none')}
    >
      <div className="space-y-3">{children}</div>
    </Disclosure>
  );
}
