'use client';

/**
 * LightControls — one lamp, with the controls it can take (ADR-369, Task 9.2).
 *
 * The controls ARE the lamp's capabilities, read from the bridge: a plug only
 * switches, a dimmable bulb also dims, an ambiance lamp also takes a colour
 * temperature within ITS range, a colour lamp also takes a colour — drawn as the
 * colour the lamp shows now, one swatch whose press opens the platform's choice
 * panel, sent when the panel closes. The temperature comes before the colour,
 * both folded in one section until it is opened, its title saying what it holds
 * and its pill the lamp's current tone (owner, 2026-10-31). Every gesture holds
 * its value while it is sent and draws the previous one again when the bridge
 * refuses it.
 */
import { Lightbulb, Palette, Thermometer } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';

import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { LightChangeBody } from '@/hooks/useWorkbenchLights';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { lightKind, toneTitleKey } from '@/lib/workbench/lights';
import type { WorkbenchLight } from '@/lib/workbench/types';

import { CommitSlider } from './CommitSlider';

export interface LightControlsProps {
  lng: Language;
  light: WorkbenchLight;
  /** Send a change; resolves once sent and re-read, rejects (already said) when refused. */
  onChange: (change: LightChangeBody) => Promise<void>;
}

/** A colour temperature as the reader knows it: 1 000 000 / mirek kelvin, to 50 K. */
function kelvin(mirek: number): number {
  return Math.round(1_000_000 / mirek / 50) * 50;
}

export function LightControls({ lng, light, onChange }: LightControlsProps) {
  const { t } = useTranslation(lng);
  const [onDraft, setOnDraft] = useState<boolean | null>(null);
  const [colourDraft, setColourDraft] = useState<string | null>(null);
  const on = onDraft ?? light.on;
  const colour = colourDraft ?? light.color_hex;
  const tone = toneTitleKey(light);

  const send = (change: LightChangeBody, draft: () => void, settle: () => void) => {
    draft();
    void onChange(change)
      .catch(() => undefined)
      .finally(settle);
  };

  return (
    <div role="group" aria-label={light.name} className="space-y-4 rounded-lg border bg-card p-4">
      <div className="flex items-center gap-3">
        <Lightbulb
          className={cn('h-5 w-5 shrink-0', on ? 'text-primary' : 'text-muted-foreground')}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">{light.name}</p>
          <p className="text-xs text-muted-foreground">
            {t(`workbench.lights.kinds.${lightKind(light)}`)}
          </p>
        </div>
        <Switch
          checked={on}
          aria-label={t('workbench.lights.light_switch', { light: light.name })}
          onCheckedChange={next =>
            send(
              { on: next },
              () => setOnDraft(next),
              () => setOnDraft(null)
            )
          }
        />
      </div>
      {light.brightness !== null && (
        <CommitSlider
          label={t('workbench.lights.brightness')}
          value={light.brightness}
          min={0}
          max={100}
          format={value => `${Math.round(value)} %`}
          onCommit={brightness => onChange({ brightness })}
        />
      )}
      {tone !== null && (
        <Disclosure
          icon={light.supports_color ? Palette : Thermometer}
          title={t(tone)}
          // Wraps rather than cuts: beside the pill, « Température et couleur » needed
          // 156 px of 150 on a 390 px phone (measured 2026-10-31).
          titleClassName="whitespace-normal break-words"
          surface="nested"
          badge={
            <span className="inline-flex items-center gap-1.5">
              {light.mirek !== null &&
                t('workbench.lights.kelvin', { kelvin: kelvin(light.mirek) })}
              {light.supports_color && colour && (
                <span
                  data-tone-colour
                  aria-hidden="true"
                  // The dot IS data: the colour the lamp shows.
                  style={{ backgroundColor: colour }}
                  className="inline-block h-3 w-3 rounded-full border border-border"
                />
              )}
            </span>
          }
        >
          <div className="space-y-4 pt-1">
            {light.mirek_min !== null && light.mirek_max !== null && (
              <CommitSlider
                label={t('workbench.lights.temperature')}
                value={light.mirek ?? Math.round((light.mirek_min + light.mirek_max) / 2)}
                min={light.mirek_min}
                max={light.mirek_max}
                format={mirek => t('workbench.lights.kelvin', { kelvin: kelvin(mirek) })}
                onCommit={mirek => onChange({ mirek })}
              />
            )}
            {light.supports_color && (
              <ColourField
                lng={lng}
                value={colour ?? '#ffffff'}
                onPick={hex =>
                  send(
                    { color_hex: hex },
                    () => setColourDraft(hex),
                    () => setColourDraft(null)
                  )
                }
              />
            )}
          </div>
        </Disclosure>
      )}
    </div>
  );
}

/**
 * The lamp's colour as it is now: one swatch whose press opens the platform's
 * choice panel; the colour is sent when the panel closes (`change`), while it
 * moves the swatch only draws it.
 */
function ColourField({
  lng,
  value,
  onPick,
}: {
  lng: Language;
  value: string;
  onPick: (hex: string) => void;
}) {
  const { t } = useTranslation(lng);
  const id = useId();
  const picker = useRef<HTMLInputElement>(null);
  const [shown, setShown] = useState<string | null>(null);

  useEffect(() => {
    const element = picker.current;
    if (!element) return;
    const pick = () => {
      setShown(null);
      onPick(element.value);
    };
    element.addEventListener('change', pick);
    return () => element.removeEventListener('change', pick);
  }, [onPick]);

  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <Label id={`${id}-label`} htmlFor={id}>
        {t('workbench.lights.colour')}
      </Label>
      <input
        ref={picker}
        id={id}
        type="color"
        aria-labelledby={`${id}-label`}
        value={shown ?? value}
        onChange={event => setShown(event.target.value)}
        className={cn(
          'h-9 w-14 shrink-0 cursor-pointer rounded-md border bg-transparent p-0',
          // The swatch is the colour itself, edge to edge, in every engine.
          '[&::-webkit-color-swatch-wrapper]:p-0 [&::-webkit-color-swatch]:rounded-[5px] [&::-webkit-color-swatch]:border-0',
          '[&::-moz-color-swatch]:rounded-[5px] [&::-moz-color-swatch]:border-0',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
        )}
      />
    </div>
  );
}
