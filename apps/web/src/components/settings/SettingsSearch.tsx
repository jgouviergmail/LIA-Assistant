'use client';

/**
 * "Search a setting" — the quick way into thirty accordion sections.
 *
 * The settings page stacks thirty user-facing sections across two tabs, all
 * collapsed. Finding one meant knowing which tab it lived in and scrolling. A
 * deep link solved that for the seventeen destinations other surfaces link to;
 * this field solves it for a reader who only knows what the setting is called.
 *
 * ## Shape constraints, not preferences
 *
 * The field lives INSIDE the sticky tab bar, so two things are load-bearing:
 *
 *  1. its height never changes. `SettingsSection`'s `scroll-mt` is calibrated
 *     against the total height of the sticky chrome, so a row that grew when
 *     results appeared would make every deep link land under the bar. Results,
 *     counts and notices therefore render in an ABSOLUTELY positioned popup,
 *     never in the flow;
 *  2. the result list is never truncated. A silent top-N reads as "nothing else
 *     matches"; the listbox scrolls instead.
 *
 * ## Accessibility
 *
 * A WAI-ARIA 1.2 combobox, built like its sibling `AdminUserAutocomplete`:
 * `role="combobox"` on the input with `aria-controls`/`aria-activedescendant`,
 * a real `listbox`/`option` tree, arrow keys wrapping around, Enter to pick,
 * Escape to dismiss then to clear. Options are selected on `mousedown` so the
 * input never blurs first. The result count is announced through a
 * visually-hidden live region — the popup itself is not a status.
 */

import { Search, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  buildSettingsSearchIndex,
  matchSettingsSections,
  type SettingsSearchAvailability,
  type SettingsSearchResult,
} from '@/lib/settings-search';
import { cn, findNormalizedMatches, normalizeSearchText } from '@/lib/utils';
import { trackSettingsSearch } from '@/lib/product-telemetry';

export interface SettingsSearchProps {
  lng: Language;
  /** What this user and this instance actually expose; see the search module. */
  availability: SettingsSearchAvailability;
  /** Picked result — the page owns the navigation and the focus move. */
  onSelect: (result: SettingsSearchResult) => void;
}

/** DOM id of the popup listbox, shared by `aria-controls`. */
const LISTBOX_ID = 'settings-search-listbox';
const optionId = (index: number): string => `settings-search-option-${index}`;

/**
 * Text with the query occurrences wrapped in `<mark>`.
 *
 * Rendered as React children rather than through `dangerouslySetInnerHTML`:
 * the query comes from the user, so the safest form is the one where it is
 * never turned into markup at all. Locating the matches is delegated to
 * `findNormalizedMatches`, the accent- and apostrophe-aware matcher the rest of
 * the search stack uses, so the highlight lands on the ORIGINAL characters —
 * typing "theme" highlights "Thème".
 */
function Highlight({ text, query }: { text: string; query: string }) {
  const ranges = findNormalizedMatches(text, normalizeSearchText(query.trim()));
  if (ranges.length === 0) return <>{text}</>;

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  ranges.forEach((range, index) => {
    if (range.start > cursor) parts.push(text.slice(cursor, range.start));
    parts.push(
      <mark key={index} className="rounded bg-primary/20 px-0.5 text-inherit">
        {text.slice(range.start, range.end)}
      </mark>
    );
    cursor = range.end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

export function SettingsSearch({ lng, availability, onSelect }: SettingsSearchProps) {
  const { t } = useTranslation(lng);

  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  /**
   * The option the reader has walked to — RAW, and never read directly.
   *
   * Typing shrinks the result list under it, so the stored index can point past
   * the end. That is clamped during render rather than repaired in an effect:
   * a `setState` inside an effect renders once with the stale value before
   * fixing it, and it is what the react-hooks ratchet forbids.
   */
  const [activeOption, setActiveOption] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // `t` changes identity when the language or the loaded resources change, so a
  // language switch rebuilds the index instead of leaving it in the old one.
  const index = useMemo(
    () => buildSettingsSearchIndex(key => t(key), availability),
    [t, availability]
  );
  const results = useMemo(() => matchSettingsSections(index, query), [index, query]);

  const isSearching = query.trim().length > 0;
  const showPopup = open && isSearching;
  /** Derived, never stored: see `activeOption`. */
  const activeIndex = activeOption < results.length ? activeOption : -1;

  // Keep the walked-to option in view. `aria-activedescendant` advertises it
  // WITHOUT moving focus — which is what keeps typing working — so the browser
  // does no scrolling of its own: past the eighth result the arrow key would
  // move an option the reader cannot see. `block: 'nearest'` scrolls the
  // listbox by the minimum and leaves the page alone.
  useEffect(() => {
    if (activeIndex < 0) return;
    document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, []);

  // Product telemetry (ADR-178 Phase 4): ONE outcome per settled query —
  // debounced so keystrokes never spam; inert unless telemetry is enabled.
  useEffect(() => {
    if (!isSearching) return undefined;
    const timer = window.setTimeout(() => {
      trackSettingsSearch(results.length === 0 ? 'zero_results' : 'results');
    }, 800);
    return () => window.clearTimeout(timer);
  }, [isSearching, query, results.length]);

  const reset = useCallback(() => {
    setQuery('');
    setOpen(false);
    setActiveOption(-1);
  }, []);

  const choose = useCallback(
    (result: SettingsSearchResult) => {
      trackSettingsSearch('result_used');
      // Cleared before handing over: the page moves focus to the section, and a
      // stale query would reopen this popup the next time the field is focused.
      reset();
      onSelect(result);
    },
    [onSelect, reset]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'Escape') {
        // APG: dismiss the popup first; a second press clears the field.
        event.preventDefault();
        if (showPopup) {
          setOpen(false);
          setActiveOption(-1);
        } else {
          reset();
        }
        return;
      }

      const count = results.length;
      if (count === 0) return;

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          setOpen(true);
          setActiveOption((activeIndex + 1) % count);
          break;
        case 'ArrowUp':
          event.preventDefault();
          setOpen(true);
          setActiveOption(activeIndex <= 0 ? count - 1 : activeIndex - 1);
          break;
        case 'Enter':
          if (showPopup && activeIndex >= 0 && activeIndex < count) {
            event.preventDefault();
            choose(results[activeIndex]);
          }
          break;
      }
    },
    [results, showPopup, activeIndex, choose, reset]
  );

  return (
    // `mb-2`, not `mt-2`: the field now sits ABOVE the tab row inside the
    // sticky bar (2026-07-30), so the gap it owns is the one to the tabs
    // below it. The bar's own `py-2` supplies the space above.
    <div ref={containerRef} className="relative mb-2">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={showPopup}
        aria-controls={LISTBOX_ID}
        aria-autocomplete="list"
        aria-activedescendant={showPopup && activeIndex >= 0 ? optionId(activeIndex) : undefined}
        aria-label={t('settings.search.label')}
        placeholder={t('settings.search.placeholder')}
        // The browser's own suggestion dropdown would paint OVER the listbox
        // and hijack the arrow keys; APG's combobox examples turn it off for
        // exactly that reason. Spellcheck squiggles on a section name are noise.
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={event => {
          setQuery(event.target.value);
          setOpen(true);
          setActiveOption(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        className={cn(
          'flex h-9 w-full rounded-lg border border-input bg-background pl-10 pr-10 text-base shadow-sm',
          'transition-colors placeholder:text-muted-foreground md:text-sm',
          'hover:border-primary/50 focus-visible:border-primary focus-visible:outline-none',
          'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1'
        )}
      />
      {isSearching && (
        <button
          type="button"
          onClick={() => {
            reset();
            inputRef.current?.focus();
          }}
          aria-label={t('settings.search.clear')}
          className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}

      {/* Announced, not shown: the count must reach a screen reader without
          adding a pixel to the sticky bar. */}
      <div role="status" aria-live="polite" className="sr-only">
        {isSearching
          ? results.length > 0
            ? t('settings.search.results_count', { count: results.length })
            : t('settings.search.no_results', { query: query.trim() })
          : ''}
      </div>

      {showPopup && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-lg border border-border bg-popover/85 backdrop-blur-md shadow-lg">
          {results.length > 0 ? (
            <ul
              id={LISTBOX_ID}
              role="listbox"
              aria-label={t('settings.search.results_label')}
              className="max-h-72 overflow-y-auto py-1"
            >
              {results.map((result, position) => (
                <li
                  key={result.token}
                  id={optionId(position)}
                  role="option"
                  aria-selected={position === activeIndex}
                  // mousedown, not click: selecting must happen before the input
                  // blurs and the outside-click handler closes the popup.
                  onMouseDown={event => {
                    event.preventDefault();
                    choose(result);
                  }}
                  onMouseEnter={() => setActiveOption(position)}
                  className={cn(
                    'cursor-pointer px-3 py-2',
                    position === activeIndex ? 'bg-accent' : 'hover:bg-accent/50'
                  )}
                >
                  <span className="block truncate text-sm font-medium">
                    <Highlight text={result.title} query={query} />
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                    {t(`settings.tabs.${result.target.tab}`)}
                    {' › '}
                    {t(`settings.groups.${result.group}`)}
                  </span>
                  {/* Only when the title did not match: otherwise the line
                      repeats what the reader can already see, and a result
                      matched on its description looks arbitrary without it. */}
                  {result.matchedIn !== 'title' && (
                    // `text-muted-foreground`, NOT `/80`. The opacity modifier
                    // read as a nice third level of hierarchy and measured
                    // 3.51:1 against the popover background — under the 4.5:1
                    // WCAG AA floor for 12 px text (caught by the axe journey
                    // that scans this popup open). Hierarchy comes from the
                    // medium-weight title instead.
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      <Highlight text={result.description} query={query} />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-3 py-3">
              <p className="text-sm">{t('settings.search.no_results', { query: query.trim() })}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t('settings.search.no_results_hint')}
              </p>
            </div>
          )}
          {/* Said once, plainly: for a superuser the search covers two tabs of
              three, and staying silent about it would be the lie. */}
          {availability.isSuperuser && (
            <p className="border-t border-border/60 px-3 py-2 text-xs text-muted-foreground">
              {t('settings.search.admin_not_indexed')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
