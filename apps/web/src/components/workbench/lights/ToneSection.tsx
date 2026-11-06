'use client';

/**
 * ToneSection — the colour temperature and the colour of a lamp or of a whole room (ADR-369).
 *
 * One folded section, named by what it holds, its pill saying the current tone (owner,
 * 2026-10-31). The temperature comes before the colour. A colour is drawn as what the lamp shows
 * now, one swatch whose press opens the platform's choice panel, sent when the panel closes.
 */
import { Palette, Thermometer } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';

import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { toneTitleKey, type ToneOffer } from '@/lib/workbench/lights';

import { CommitSlider } from './CommitSlider';

export interface ToneSectionProps {
  lng: Language;
  /** What the lamp, or every lamp of the room, can take. */
  offer: ToneOffer;
  /** The temperature it shows now, if it reports one. */
  mirek: number | null;
  /** The colour it shows now, if it reports one. */
  colour: string | null;
  /** Send a temperature; resolves once sent and re-read, rejects when refused. */
  onTemperature: (mirek: number) => Promise<void>;
  onColour: (hex: string) => void;
}

/** A colour temperature as the reader knows it: 1 000 000 / mirek kelvin, to 50 K. */
function kelvin(mirek: number): number {
  return Math.round(1_000_000 / mirek / 50) * 50;
}

export function ToneSection({
  lng,
  offer,
  mirek,
  colour,
  onTemperature,
  onColour,
}: ToneSectionProps) {
  const { t } = useTranslation(lng);
  const title = toneTitleKey(offer);
  if (title === null) return null;
  return (
    <Disclosure
      icon={offer.supports_color ? Palette : Thermometer}
      title={t(title)}
      // Wraps rather than cuts: beside the pill, « Température et couleur » needed
      // 156 px of 150 on a 390 px phone (measured 2026-10-31).
      titleClassName="whitespace-normal break-words"
      surface="nested"
      badge={
        <span className="inline-flex items-center gap-1.5">
          {mirek !== null && t('workbench.lights.kelvin', { kelvin: kelvin(mirek) })}
          {offer.supports_color && colour && (
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
        {offer.mirek_min !== null && offer.mirek_max !== null && (
          <CommitSlider
            label={t('workbench.lights.temperature')}
            value={mirek ?? Math.round((offer.mirek_min + offer.mirek_max) / 2)}
            min={offer.mirek_min}
            max={offer.mirek_max}
            format={value => t('workbench.lights.kelvin', { kelvin: kelvin(value) })}
            onCommit={onTemperature}
          />
        )}
        {offer.supports_color && (
          <ColourField lng={lng} value={colour ?? '#ffffff'} onPick={onColour} />
        )}
      </div>
    </Disclosure>
  );
}

/**
 * The colour as it is now: one swatch whose press opens the platform's choice panel; the colour
 * is sent when the panel closes (`change`), while it moves the swatch only draws it.
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
