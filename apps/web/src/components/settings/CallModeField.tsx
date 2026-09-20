'use client';
/**
 * How the person's own calls run — Live or Live direct (ADR-301).
 *
 * The two options carry the live mode's own names and marks: « Live », where
 * the voice on the phone hands every request to the chat and LIA acts in
 * the person's own conversation (the browser's Live mode, on a phone line),
 * and « Live direct », where the voice reads LIA's tools itself and the call
 * is relayed to the chat at its end. One `GlyphSelect`, like every list of a
 * mode in the application (lot 21), so the choice reads the same everywhere.
 *
 * Live is the default. When this instance cannot run it — the vendor cannot
 * call the API back — the choice stays stored but the list is disabled and
 * says which mode a call will actually run, so the page never offers a mode
 * the dial path will not honour (ADR-184).
 */
import { AudioLines, Radio } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import { GlyphSelect } from '@/components/workboard/GlyphSelect';
import { PHONE_CALL_MODES, type PhoneCallMode, type TelephonyIdentity } from '@/types/telephony';
import type { Language } from '@/i18n/settings';

export interface CallModeFieldProps {
  lng: Language;
  /** Id of the control, so its label points at it. */
  id: string;
  identity: TelephonyIdentity;
  busy: boolean;
  onChange: (mode: PhoneCallMode) => Promise<string | null>;
}

const GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';

/** The mark of each mode: a live line for Live, a broadcast for Live direct. */
export function callModeIcon(mode: PhoneCallMode, className: string = GLYPH) {
  return mode === 'delegated' ? (
    <AudioLines className={className} aria-hidden="true" />
  ) : (
    <Radio className={className} aria-hidden="true" />
  );
}

export function CallModeField({ lng, id, identity, busy, onChange }: CallModeFieldProps) {
  const { t } = useTranslation(lng);
  const items = PHONE_CALL_MODES.map(mode => ({
    value: mode,
    glyph: callModeIcon(mode),
    text: t(`settings.telephony.identity.call_mode.${mode}`),
  }));
  const unavailable = !identity.live_available;

  return (
    <div className="space-y-2 rounded-lg border bg-card p-3">
      <GlyphSelect
        id={id}
        hideLabel={false}
        label={t('settings.telephony.identity.call_mode.label')}
        value={identity.call_mode}
        items={items}
        disabled={busy || unavailable}
        className="h-10 px-3 text-sm"
        onChange={chosen => {
          // The list only ever offers the two modes; narrowing by lookup keeps
          // the type honest without a cast.
          const mode = PHONE_CALL_MODES.find(candidate => candidate === chosen);
          if (mode) void onChange(mode);
        }}
      />
      <p className="text-xs text-muted-foreground">
        {t(`settings.telephony.identity.call_mode.help_${identity.call_mode}`)}
      </p>
      {unavailable && (
        <p role="status" className="text-xs text-warning">
          {t('settings.telephony.identity.call_mode.unavailable', {
            reason: t(
              `settings.telephony.identity.call_mode.reasons.${identity.live_unavailable_reason ?? 'unknown'}`
            ),
            mode: t(`settings.telephony.identity.call_mode.${identity.call_mode_effective}`),
          })}
        </p>
      )}
    </div>
  );
}
