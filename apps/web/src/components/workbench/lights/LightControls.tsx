'use client';

/**
 * LightControls — one lamp, with the controls it can take (ADR-369, Task 9.2).
 *
 * The controls ARE the lamp's capabilities, read from the bridge: a plug only
 * switches, a dimmable bulb also dims, an ambiance lamp also takes a colour
 * temperature within ITS range, a colour lamp also takes a colour (`ToneSection`).
 * Every gesture holds its value while it is sent and draws the previous one again
 * when the bridge refuses it. A lamp the bridge cannot reach says so and offers
 * nothing: a bridge accepts what it cannot deliver, so the gesture would read as done.
 */
import { Lightbulb, TriangleAlert } from '@/lib/icons';
import { useEffect, useRef, useState } from 'react';

import { Switch } from '@/components/ui/switch';
import type { LightChangeBody } from '@/hooks/useWorkbenchLights';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { UNLIT_CARD, lightKind } from '@/lib/workbench/lights';
import type { WorkbenchLight } from '@/lib/workbench/types';

import { CommitSlider } from './CommitSlider';
import { ToneSection } from './ToneSection';

export interface LightControlsProps {
  lng: Language;
  light: WorkbenchLight;
  /** Send a change; resolves once sent and re-read, rejects (already said) when refused. */
  onChange: (change: LightChangeBody) => Promise<void>;
  /** A source card selected this actual lamp; focusing it sends no command. */
  targeted?: boolean;
}

export function LightControls({ lng, light, onChange, targeted = false }: LightControlsProps) {
  const { t } = useTranslation(lng);
  const [onDraft, setOnDraft] = useState<boolean | null>(null);
  const [colourDraft, setColourDraft] = useState<string | null>(null);
  const on = onDraft ?? light.on;
  const colour = colourDraft ?? light.color_hex;
  const reachable = light.reachable !== false;
  const card = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (targeted) card.current?.focus();
  }, [targeted, light.id]);

  const send = (change: LightChangeBody, draft: () => void, settle: () => void) => {
    draft();
    void onChange(change)
      .catch(() => undefined)
      .finally(settle);
  };

  return (
    <div
      ref={card}
      role="group"
      aria-label={light.name}
      aria-current={targeted ? 'true' : undefined}
      tabIndex={targeted ? -1 : undefined}
      data-lit={on && reachable}
      className={cn(
        UNLIT_CARD,
        'space-y-4 rounded-lg border bg-card p-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
      )}
    >
      <div className="flex items-center gap-3">
        <Lightbulb
          className={cn('h-5 w-5 shrink-0', on ? 'text-primary' : 'text-muted-foreground')}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              'truncate text-sm font-semibold',
              reachable ? 'text-foreground' : 'text-muted-foreground'
            )}
          >
            {light.name}
          </p>
          <p className="text-xs text-muted-foreground">
            {t(`workbench.lights.kinds.${lightKind(light)}`)}
          </p>
        </div>
        <Switch
          checked={on}
          disabled={!reachable}
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
      {!reachable && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <TriangleAlert className="h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          {t('workbench.lights.light_unreachable')}
        </p>
      )}
      {reachable && light.brightness !== null && (
        <CommitSlider
          label={t('workbench.lights.brightness')}
          value={light.brightness}
          min={0}
          max={100}
          format={value => `${Math.round(value)} %`}
          onCommit={brightness => onChange({ brightness })}
        />
      )}
      {reachable && (
        <ToneSection
          lng={lng}
          offer={light}
          mirek={light.mirek}
          colour={colour}
          onTemperature={mirek => onChange({ mirek })}
          onColour={hex =>
            send(
              { color_hex: hex },
              () => setColourDraft(hex),
              () => setColourDraft(null)
            )
          }
        />
      )}
    </div>
  );
}
