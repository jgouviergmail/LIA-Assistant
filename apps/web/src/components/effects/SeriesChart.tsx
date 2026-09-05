'use client';

/**
 * SeriesChart — one bounded series, drawn once (ADR-263).
 *
 * Every chart on the registers surfaces goes through here, so they cannot drift
 * into ten slightly different bar charts. What varies is declared, not coded
 * again: the wording, the unit, whether a second measure stacks on the same
 * bar, and what an empty series should say.
 *
 * Three decisions the shape enforces:
 *
 * - **Horizontal bars.** The labels are model names, graph nodes and tool
 *   names — long, and unreadable rotated under a vertical axis on a phone.
 * - **The exact figure is shown beside the title, and it SAYS what it is.**
 *   The server folds a long tail into « other »; without it a reader could not
 *   check the bars, and a chart that cannot be checked is decoration (ADR-185).
 *   Whether it is a total or a mean comes from the series' own `kind`, never
 *   from the caller — a chart added tomorrow cannot label it wrongly.
 * - **An empty series SAYS it is empty.** A blank card reads as a broken one,
 *   and for the integrity series empty is the good news — it deserves a
 *   sentence, not a void.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { StatisticsSeries } from '@/hooks/useRegisterStatistics';

/**
 * Tooltip styling pinned to the popover tokens so it follows the active theme.
 * Without it recharts renders a white card with light-grey labels — unreadable
 * in dark mode (the same override `HealthMetricsCharts` already carries).
 */
const TOOLTIP_CONTENT_STYLE: React.CSSProperties = {
  backgroundColor: 'var(--color-popover)',
  borderColor: 'var(--color-border)',
  borderRadius: '6px',
  color: 'var(--color-popover-foreground)',
};
const TOOLTIP_ITEM_STYLE: React.CSSProperties = { color: 'var(--color-popover-foreground)' };

/** Height per bar, so a two-bar chart is not as tall as a twelve-bar one. */
const ROW_HEIGHT = 28;
const MIN_HEIGHT = 120;

export interface SeriesChartProps {
  title: string;
  /** What the numbers mean, in one line. */
  description?: string;
  series: StatisticsSeries | undefined;
  /** Shown instead of the chart when the series holds nothing. */
  emptyLabel: string;
  /** Legend for the main measure. */
  countLabel: string;
  /** Legend for the second measure; its presence is what stacks the bars. */
  secondaryLabel?: string;
  /** Appended to every value — « ms », say. */
  unit?: string;
  /** Renders a raw label into the reader's language. */
  renderLabel?: (label: string) => string;
  /** Palette index, so neighbouring cards do not share a colour. */
  tone?: 'primary' | 'success' | 'warning' | 'destructive';
}

const TONES: Record<NonNullable<SeriesChartProps['tone']>, string> = {
  primary: 'var(--color-primary)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  destructive: 'var(--color-destructive)',
};

export function SeriesChart({
  title,
  description,
  series,
  emptyLabel,
  countLabel,
  secondaryLabel,
  unit,
  renderLabel,
  tone = 'primary',
}: SeriesChartProps) {
  const { t } = useTranslation();
  const rows = useMemo(
    () =>
      (series?.slices ?? []).map(slice => ({
        label: renderLabel ? renderLabel(slice.label) : slice.label,
        count: slice.count,
        secondary: slice.secondary,
      })),
    [series, renderLabel]
  );

  const height = Math.max(MIN_HEIGHT, rows.length * ROW_HEIGHT + 24);
  const format = (value: number) => (unit ? `${value} ${unit}` : String(value));
  // « Total 320 ms » and « Average 80 ms » are different claims about the same
  // bars; the series declares which one it supports.
  const badge =
    series &&
    t(`registers.charts.badge.${series.kind ?? 'count'}`, {
      value: format(series.total),
      defaultValue: format(series.total),
    });

  return (
    <Card className="min-w-0">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <h3 className="text-sm font-medium">{title}</h3>
            {description && <p className="text-xs text-muted-foreground">{description}</p>}
          </div>
          {series !== undefined && (
            // The exact figure, beside the bars it must be checkable against.
            <Badge variant="secondary" className="shrink-0">
              {badge}
            </Badge>
          )}
        </div>

        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{emptyLabel}</p>
        ) : (
          <div style={{ width: '100%', height }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 16 }}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--color-border)"
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11 }}
                  stroke="var(--color-muted-foreground)"
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={128}
                  tick={{ fontSize: 11 }}
                  stroke="var(--color-muted-foreground)"
                  interval={0}
                />
                <Tooltip
                  contentStyle={TOOLTIP_CONTENT_STYLE}
                  itemStyle={TOOLTIP_ITEM_STYLE}
                  cursor={{ fill: 'var(--color-muted)', opacity: 0.3 }}
                  // recharts hands the formatter a widened value type; a
                  // narrow signature here compiles today and breaks on the next
                  // upgrade, so the narrowing happens in the body.
                  formatter={(value, name) => [
                    format(typeof value === 'number' ? value : Number(value ?? 0)),
                    String(name ?? ''),
                  ]}
                />
                <Bar dataKey="count" name={countLabel} stackId="one" radius={[0, 3, 3, 0]}>
                  {rows.map((row, index) => (
                    <Cell key={row.label} fill={TONES[tone]} opacity={index === 0 ? 1 : 0.75} />
                  ))}
                </Bar>
                {secondaryLabel && (
                  <Bar
                    dataKey="secondary"
                    name={secondaryLabel}
                    stackId="one"
                    fill={TONES.warning}
                    radius={[0, 3, 3, 0]}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
