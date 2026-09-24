'use client';

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MapsFormat } from '@/lib/maps/format';
import { chartScale, type MonthCount } from '@/lib/maps/timeline';
import type { ThemeView } from '@/lib/maps/types';
import { cn } from '@/lib/utils';

const WIDTH = 1100;
const HEIGHT = 320;
const MARGIN = { left: 44, right: 12, top: 22, bottom: 46 };

const round = (n: number): number => Math.round(n * 10) / 10;

interface Tip {
  month: string;
  x: number;
  y: number;
  /** The pointer is in the right half: the tip opens leftward, so it never leaves the screen. */
  flipX: boolean;
  /** The pointer is in the lower half: the tip opens upward. */
  flipY: boolean;
}

function tipAt(month: string, event: React.MouseEvent): Tip {
  return {
    month,
    x: event.clientX,
    y: event.clientY,
    flipX: event.clientX > window.innerWidth / 2,
    flipY: event.clientY > window.innerHeight / 2,
  };
}

/** Where a month's block starts in the timeline. */
export const monthAnchor = (month: string): string => `lm-month-${month}`;

/**
 * Decisions per month, stacked by theme. The chart is an image for assistive
 * technology — its label states the span, and the timeline below it carries
 * every decision in text — while a pointer gets the per-theme breakdown of a
 * month and can jump to it.
 */
export function DecisionChart({
  months,
  themes,
  activeThemes,
  format,
}: {
  months: readonly MonthCount[];
  themes: readonly ThemeView[];
  /** Themes the timeline is filtered on (the others fade). */
  activeThemes: ReadonlySet<string>;
  format: MapsFormat;
}) {
  const { t } = useTranslation();
  const [tip, setTip] = useState<Tip | null>(null);
  const themeById = useMemo(() => new Map(themes.map(th => [th.id, th])), [themes]);
  const max = Math.max(1, ...months.map(m => m.total));
  const { step, top } = chartScale(max);
  const plotW = WIDTH - MARGIN.left - MARGIN.right;
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const slot = plotW / Math.max(1, months.length);
  const barW = Math.min(56, slot * 0.64);
  const y = (v: number): number => MARGIN.top + plotH - (v / top) * plotH;
  const ticks = Array.from({ length: Math.floor(top / step) + 1 }, (_, i) => i * step);
  const filtered = activeThemes.size > 0;
  const span =
    months.length > 0
      ? { from: format.month(months[0].month), to: format.month(months[months.length - 1].month) }
      : { from: '', to: '' };
  const tipMonth = tip ? months.find(m => m.month === tip.month) : undefined;

  return (
    <>
      <svg
        className={cn('lm-chart', filtered && 'is-filtered')}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={t('maps.history.chart_label', span)}
        onMouseLeave={() => setTip(null)}
      >
        <g className="lm-axis">
          {ticks.map(v => (
            <g key={v}>
              <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={round(y(v))} y2={round(y(v))} />
              <text x={MARGIN.left - 8} y={round(y(v) + 4)} textAnchor="end">
                {format.number(v)}
              </text>
            </g>
          ))}
          {months.map((m, i) => (
            <text
              key={m.month}
              x={round(MARGIN.left + i * slot + slot / 2)}
              y={HEIGHT - MARGIN.bottom + 22}
              textAnchor="middle"
            >
              {format.monthAxis(m.month)}
            </text>
          ))}
        </g>
        <g>
          {months.map((m, i) => {
            const x = MARGIN.left + i * slot + (slot - barW) / 2;
            let acc = 0;
            return (
              <g key={m.month}>
                {m.byTheme.map(({ theme, count }) => {
                  const y0 = y(acc);
                  const y1 = y(acc + count);
                  acc += count;
                  return (
                    <rect
                      key={theme}
                      className={cn('lm-bar', filtered && !activeThemes.has(theme) && 'is-off')}
                      data-tone={themeById.get(theme)?.tone}
                      x={round(x)}
                      y={round(y1)}
                      width={round(barW)}
                      height={round(Math.max(0.8, y0 - y1 - 1))}
                      rx={2}
                      onMouseMove={event => setTip(tipAt(m.month, event))}
                      onClick={() =>
                        document
                          .getElementById(monthAnchor(m.month))
                          ?.scrollIntoView({ block: 'start' })
                      }
                    />
                  );
                })}
                {m.total > 0 && (
                  <text className="lm-total" x={round(x + barW / 2)} y={round(y(m.total) - 7)}>
                    {format.number(m.total)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
      {tip && tipMonth && (
        <div
          className="lm-tip"
          aria-hidden="true"
          style={{
            left: tip.x,
            top: tip.y,
            transform: `translate(${tip.flipX ? 'calc(-100% - 14px)' : '14px'}, ${tip.flipY ? 'calc(-100% - 12px)' : '16px'})`,
          }}
        >
          <b>{`${format.month(tipMonth.month)} · ${format.number(tipMonth.total)}`}</b>
          {tipMonth.byTheme.map(({ theme, count }) => (
            <div key={theme}>
              {t('maps.history.tip_line', {
                theme: themeById.get(theme)?.name ?? theme,
                value: format.number(count),
              })}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
