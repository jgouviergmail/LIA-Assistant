'use client';
/**
 * What the board is narrowed to (ADR-276).
 *
 * The same glyph lists the cards and the panel carry (D81): a filter's items
 * wear the marks of what they narrow to — a person, a ranked priority, a
 * sort key — and « any » wears ONE sign wherever it appears. Every control
 * is labelled with its family's glyph, and the search box is debounced by
 * the caller's own state rather than firing a request per keystroke.
 */
import { useTranslation } from 'react-i18next';
import { Filter, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { GlyphLabel, GlyphSelect } from '@/components/workboard/GlyphSelect';
import { PRIORITY_ANY, PrioritySelect } from '@/components/workboard/PrioritySelect';
import type { Language } from '@/i18n/settings';
import { SEARCH_MAX_CHARS } from '@/lib/workboard/filters-url';
import { anyIcon, filterIcon, partyIcon, sortIcon } from '@/lib/workboard/icons';
import type { BoardFilters as Filters, BoardSide, BoardSort } from '@/types/workboard';

const SIDES: readonly BoardSide[] = ['all', 'me', 'lia', 'peer'];
const SORTS: readonly BoardSort[] = ['position', 'priority', 'due', 'updated', 'created'];

export interface BoardFiltersProps {
  lng: Language;
  filters: Filters;
  onChange: (filters: Filters) => void;
}

/** The family glyph in a label, and the glyph on each item. */
const LABEL_GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';
const ITEM_GLYPH = 'h-3.5 w-3.5 shrink-0';
const ANY_GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';
const FIELD = 'h-10 px-3 text-sm';

export function BoardFilters({ filters, onChange }: BoardFiltersProps) {
  const { t } = useTranslation();
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });

  return (
    <section
      aria-label={t('workboard.filters.title')}
      className="rounded-xl border border-border/50 bg-muted/20 p-3"
    >
      {/* A title always carries an icon, in the theme colour. « Clear »
          belongs on the title's own line: at the end of a wrapping row of
          controls it landed wherever the last field happened to stop. */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Filter className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('workboard.filters.title')}
        </h2>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange({ assignee: 'all', sort: 'position' })}
        >
          <X className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          {t('workboard.filters.reset')}
        </Button>
      </div>

      {/* A GRID, never a wrapping row of fixed widths: those left one field
          alone on its line at some widths and three on others, so nothing
          lined up with anything. One column on a phone, two from `sm`, four
          from `xl` — the fields share the width and their labels sit on the
          same baselines. */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
    </section>
  );
}
