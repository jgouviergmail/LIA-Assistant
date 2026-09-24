'use client';

import { ArrowUpRight, Filter, RotateCcw, Search, Tag, X } from 'lucide-react';
import { useEffect, useId, useMemo, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { DecisionChart, monthAnchor } from './DecisionChart';
import { MapIcon } from './map-icons';
import { BrickChip } from './MapLink';
import { SectionHead } from './SectionHead';
import type { Language } from '@/i18n/settings';
import { mapsFormat, type MapsFormat } from '@/lib/maps/format';
import { decisionFileUrl, decisionHash, releaseUrl } from '@/lib/maps/links';
import {
  INITIAL_FILTERS,
  adrLabel,
  buildTimeline,
  decisionOfHash,
  filtersReducer,
  monthlyCounts,
  type EraGroup,
  type TimelineItem,
} from '@/lib/maps/timeline';
import type { HistoryView, ThemeView } from '@/lib/maps/types';
import { setMapHash, useMapHash } from '@/lib/maps/use-map-hash';
import { cn } from '@/lib/utils';

function DecisionItem({
  item,
  view,
  themes,
  target,
  format,
  lng,
}: {
  item: TimelineItem;
  view: HistoryView;
  themes: ReadonlyMap<string, ThemeView>;
  target: number | null;
  format: MapsFormat;
  lng: Language;
}) {
  const { t } = useTranslation();
  if (item.kind === 'release') {
    return (
      <li className="is-release">
        <span className="lm-release-pin" aria-hidden="true" />
        <a
          className="lm-release"
          href={releaseUrl(view.repo, item.release.version, item.release.date)}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Tag aria-hidden="true" width={14} height={14} className="lm-ic" />
          {t('maps.history.release', {
            version: item.release.version,
            date: format.dayShort(item.release.date),
          })}
          <span className="sr-only"> {t('maps.new_tab')}</span>
        </a>
      </li>
    );
  }
  const decision = item.decision;
  const theme = themes.get(decision.theme);
  const titleId = `lm-adr-title-${decision.adr}`;
  return (
    <li>
      <span className="lm-pin" data-tone={theme?.tone} aria-hidden="true">
        {theme && <MapIcon name={theme.icon} size={15} />}
      </span>
      <article
        className={cn('lm-adr-card', target === decision.adr && 'is-target')}
        id={decisionHash(decision.adr)}
        data-tone={theme?.tone}
        aria-labelledby={titleId}
      >
        <header>
          <span className="lm-no">{adrLabel(decision.adr)}</span>
          <time dateTime={decision.date}>{format.day(decision.date)}</time>
          {theme && (
            <span className="lm-chip is-plain is-theme" data-tone={theme.tone}>
              <MapIcon name={theme.icon} size={13} />
              {theme.name}
            </span>
          )}
        </header>
        <h5 className="lm-adr-title" id={titleId}>
          {decision.title}
        </h5>
        <p>{decision.summary}</p>
        <div className="lm-foot-row">
          {decision.bricks.map(id =>
            view.refs[id] ? (
              <BrickChip key={id} brick={view.refs[id]} from="history" lng={lng} />
            ) : null
          )}
          <a
            className="lm-read"
            href={decisionFileUrl(view.repo, decision.adr, decision.file)}
            target="_blank"
            rel="noopener noreferrer"
          >
            {decision.file ? t('maps.history.read') : t('maps.history.in_index')}
            <ArrowUpRight aria-hidden="true" width={14} height={14} />
            <span className="sr-only"> {t('maps.new_tab')}</span>
          </a>
        </div>
      </article>
    </li>
  );
}

function EraSection({
  group,
  view,
  themes,
  target,
  format,
  lng,
}: {
  group: EraGroup;
  view: HistoryView;
  themes: ReadonlyMap<string, ThemeView>;
  target: number | null;
  format: MapsFormat;
  lng: Language;
}) {
  const { t } = useTranslation();
  const { era } = group;
  const range = `${format.dayShort(era.from)} – ${era.to ? format.dayShort(era.to) : t('maps.history.until_today')}`;
  return (
    <section aria-labelledby={`lm-era-${era.id}`}>
      <div className="lm-era">
        <p className="lm-kicker">
          {`${t('maps.history.chapter', { index: group.index })} · ${range} · ${t('maps.history.decisions', { count: group.count })}`}
        </p>
        <h3 className="lm-era-title" id={`lm-era-${era.id}`}>
          {era.name}
        </h3>
        <p className="lm-era-text">{era.summary}</p>
        <ul className="lm-chips">
          {group.topThemes.map(({ theme, count }) => {
            const themeView = themes.get(theme);
            return themeView ? (
              <li key={theme} className="lm-chip is-plain is-theme" data-tone={themeView.tone}>
                <MapIcon name={themeView.icon} size={13} />
                {`${themeView.name} · ${format.number(count)}`}
              </li>
            ) : null;
          })}
        </ul>
      </div>
      {group.months.map(block => (
        <div className="lm-mblock" key={block.month}>
          <div className="lm-month" id={monthAnchor(block.month)}>
            <h4 className="lm-month-title">{format.month(block.month)}</h4>
            <span>{t('maps.history.decisions', { count: block.count })}</span>
          </div>
          <ol className="lm-tl is-split">
            {block.items.map(item => (
              <DecisionItem
                key={
                  item.kind === 'decision'
                    ? `adr-${item.decision.adr}`
                    : `v-${item.release.version}`
                }
                item={item}
                view={view}
                themes={themes}
                target={target}
                format={format}
                lng={lng}
              />
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}

/**
 * The decision history: the monthly chart, the filters, and every decision in
 * its chapter and month. The page's hash is its address — `#adr-263` points at
 * a decision (and clears the filters that would hide it), `#t.redis` shows only
 * the decisions that shaped that brick.
 */
export function HistoryMap({ view, lng }: { view: HistoryView; lng: Language }) {
  const { t } = useTranslation();
  const format = useMemo(() => mapsFormat(lng), [lng]);
  const hash = useMapHash();
  const [filters, dispatch] = useReducer(filtersReducer, INITIAL_FILTERS);
  const releasesLabel = useId();
  const newestLabel = useId();
  const themes = useMemo(() => new Map(view.themes.map(th => [th.id, th])), [view.themes]);
  const target = decisionOfHash(hash);
  const brick = view.refs[hash] ? hash : null;

  const months = useMemo(() => monthlyCounts(view.decisions, view.themes), [view]);
  const timeline = useMemo(
    () => buildTimeline(view, { ...filters, brick }),
    [view, filters, brick]
  );

  // A decision the address points at is revealed and brought into view. The
  // filters give way in the reducer, from the event that moved the hash.
  useEffect(() => {
    const onHash = () => {
      const adr = decisionOfHash(window.location.hash.slice(1));
      const decision = view.decisions.find(d => d.adr === adr);
      if (decision) {
        dispatch({ type: 'reveal', decision, themeName: id => themes.get(id)?.name ?? '' });
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [view.decisions, themes]);

  useEffect(() => {
    if (target === null) return;
    document.getElementById(decisionHash(target))?.scrollIntoView({ block: 'center' });
  }, [target]);

  const reset = () => {
    dispatch({ type: 'reset' });
    setMapHash(null);
  };

  return (
    <>
      <section className="lm-section" aria-labelledby="lm-chart-title">
        <SectionHead
          id="lm-chart-title"
          kicker={t('maps.common.overview_kicker')}
          title={t('maps.history.chart_title')}
          text={t('maps.history.chart_text')}
        />
        <div className="lm-card lm-chart-card">
          <div className="lm-scroll-x">
            <DecisionChart
              months={months}
              themes={view.themes}
              activeThemes={filters.themes}
              format={format}
            />
          </div>
        </div>
      </section>

      <section className="lm-section" aria-labelledby="lm-timeline-title">
        <SectionHead
          id="lm-timeline-title"
          kicker={t('maps.history.timeline_kicker')}
          title={t('maps.history.timeline_title')}
          text={t('maps.history.timeline_text')}
        />
        <div className="lm-filters">
          <div className="lm-filter-row" role="group" aria-label={t('maps.history.themes_label')}>
            {view.themes.map(theme => (
              <button
                key={theme.id}
                type="button"
                className="lm-theme-chip"
                data-tone={theme.tone}
                aria-pressed={filters.themes.has(theme.id)}
                title={theme.summary}
                onClick={() => dispatch({ type: 'toggleTheme', theme: theme.id })}
              >
                <MapIcon name={theme.icon} size={15} />
                {theme.name}
                <span className="lm-n">{format.number(theme.count)}</span>
              </button>
            ))}
          </div>
          <div className="lm-filter-row">
            <div className="lm-search is-narrow">
              <Search aria-hidden="true" width={16} height={16} className="lm-ic" />
              <input
                type="search"
                aria-label={t('maps.history.search_label')}
                value={filters.query}
                placeholder={t('maps.history.search_placeholder')}
                autoComplete="off"
                onChange={event => dispatch({ type: 'query', value: event.target.value })}
              />
            </div>
            <label className="lm-toggle">
              <input
                type="checkbox"
                aria-labelledby={releasesLabel}
                checked={filters.releases}
                onChange={event => dispatch({ type: 'releases', value: event.target.checked })}
              />
              <span id={releasesLabel}>{t('maps.history.show_releases')}</span>
            </label>
            <label className="lm-toggle">
              <input
                type="checkbox"
                aria-labelledby={newestLabel}
                checked={filters.newestFirst}
                onChange={event => dispatch({ type: 'newestFirst', value: event.target.checked })}
              />
              <span id={newestLabel}>{t('maps.history.newest_first')}</span>
            </label>
            <button type="button" className="lm-btn" onClick={reset}>
              <RotateCcw aria-hidden="true" width={15} height={15} />
              {t('maps.history.reset')}
            </button>
            <span className="lm-result-count" aria-live="polite">
              {t('maps.history.shown', { count: timeline.shown })}
            </span>
          </div>
          {brick && view.refs[brick] && (
            <div className="lm-filter-row">
              <span className="lm-hint">
                <Filter aria-hidden="true" width={14} height={14} className="lm-ic" />
                {t('maps.history.brick_filter')}
              </span>
              <BrickChip brick={view.refs[brick]} from="history" lng={lng} />
              <button type="button" className="lm-linkish" onClick={() => setMapHash(null)}>
                <X aria-hidden="true" width={14} height={14} />
                {t('maps.history.clear_brick_filter')}
              </button>
            </div>
          )}
        </div>
        <div className="lm-timeline">
          {timeline.eras.length ? (
            timeline.eras.map(group => (
              <EraSection
                key={group.era.id}
                group={group}
                view={view}
                themes={themes}
                target={target}
                format={format}
                lng={lng}
              />
            ))
          ) : (
            <div className="lm-no-results">
              <p>{t('maps.history.empty')}</p>
              <p>
                <button type="button" className="lm-btn" onClick={reset}>
                  <RotateCcw aria-hidden="true" width={15} height={15} />
                  {t('maps.history.reset_filters')}
                </button>
              </p>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
