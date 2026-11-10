'use client';

import { useId, useRef, useState } from 'react';
import { JevGateDistribution } from '@/components/settings/JevGateDistribution';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { JevGateStatistics, JevGateStatus, JevUsage } from '@/types/jev';

const PREFIX = 'settings.admin.jev.thresholds';

/** A threshold lives at the hundredth: JEV reports its probabilities at that precision. */
function toHundredth(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatThreshold(value: number, lng: Language): string {
  return value.toLocaleString(lng, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface GateRowProps {
  lng: Language;
  usage: JevUsage;
  gate: JevGateStatus;
  /** The window's judgements of this gate, once read. */
  statistics: JevGateStatistics | undefined;
  busy: boolean;
  onCommit: (values: Record<string, number>) => Promise<void>;
}

/**
 * One gate: its slider within the published bounds, its default, its way back to it.
 *
 * The value shown while the slider moves is a draft, dropped once the server answers:
 * its value on success, the stored one on failure.
 */
function GateRow({ lng, usage, gate, statistics, busy, onCommit }: GateRowProps) {
  const { t } = useTranslation(lng, 'translation');
  const [draft, setDraft] = useState<number | null>(null);
  const sliderRoot = useRef<HTMLSpanElement>(null);
  const labelId = useId();
  const label = t(`settings.admin.jev.gates.${usage}.${gate.key}`);
  const value = draft ?? gate.value;
  const shown = formatThreshold(value, lng);

  const commit = (next: number) => {
    void onCommit({ [gate.key]: next }).finally(() => setDraft(null));
  };
  const reset = () => {
    if (busy) return;
    // The button leaves the page once the default is back: the focus goes to the
    // control it acted on, never to the document.
    sliderRoot.current?.querySelector<HTMLElement>('[role="slider"]')?.focus();
    commit(gate.default);
  };

  return (
    // A group named by its gate: a usage's resets read « Restore default » each, and
    // the group is what tells them apart.
    <div role="group" aria-labelledby={labelId} className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span id={labelId} className="text-sm font-medium">
          {label}
        </span>
        <span className="shrink-0 text-sm tabular-nums text-primary">{shown}</span>
      </div>
      <Slider
        ref={sliderRoot}
        value={[value]}
        min={gate.minimum}
        max={gate.maximum}
        step={0.01}
        onValueChange={([next]) => {
          if (!busy) setDraft(toHundredth(next));
        }}
        onValueCommit={([next]) => {
          if (!busy) commit(toHundredth(next));
        }}
        aria-label={t(`${PREFIX}.sliderLabel`, { gate: label })}
        thumbProps={{ 'aria-valuetext': shown, 'aria-disabled': busy }}
      />
      <div className="flex min-h-8 flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{t(`${PREFIX}.default`, { value: formatThreshold(gate.default, lng) })}</span>
        {value !== gate.default && (
          <Button variant="ghost" size="sm" aria-disabled={busy} onClick={reset}>
            {t(`${PREFIX}.reset`)}
          </Button>
        )}
      </div>
      {gate.kind === 'margin' && (
        <p className="text-xs leading-relaxed text-muted-foreground">{t(`${PREFIX}.marginHelp`)}</p>
      )}
      {gate.scope === 'all' && (
        <p className="text-xs leading-relaxed text-muted-foreground">{t(`${PREFIX}.scopeAll`)}</p>
      )}
      {statistics && <JevGateDistribution lng={lng} statistics={statistics} value={value} />}
    </div>
  );
}

/** The thresholds of one JEV usage (ADR-374), each within the bounds the server publishes. */
export function JevGateThresholds({
  lng,
  usage,
  gates,
  statistics,
  busy,
  onCommit,
}: {
  lng: Language;
  usage: JevUsage;
  gates: JevGateStatus[];
  /** The window's judgements of each gate, once read. */
  statistics: JevGateStatistics[] | undefined;
  busy: boolean;
  onCommit: (values: Record<string, number>) => Promise<void>;
}) {
  return (
    <div className="space-y-5">
      {gates.map(gate => (
        <GateRow
          key={gate.key}
          lng={lng}
          usage={usage}
          gate={gate}
          statistics={statistics?.find(entry => entry.key === gate.key)}
          busy={busy}
          onCommit={onCommit}
        />
      ))}
    </div>
  );
}
