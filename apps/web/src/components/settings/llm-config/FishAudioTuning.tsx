'use client';

/**
 * Fish Audio tuning for a voice slot (ADR-345): the container, the
 * latency/quality trade-off, the transport (HTTP, or one WebSocket session per
 * sentence), the speaking rate — and the public voices the instance pins by id.
 *
 * Every option offered is one the client accepts (the lists mirror
 * ``voice/fishaudio/formats.py``, held equal by a backend guard). A public
 * voice of the vendor's library is mostly a clone nobody licensed, so a pin is
 * offered only after the voice was read (a trained speech voice the vendor
 * serves) AND the administrator attested holding the right to use it. The pins
 * are ONE list for every voice slot (amendment 2026-10-14): pinning and
 * unpinning are acts of their own, immediate and filed in the admin audit log
 * with the attestation — never part of the slot's save.
 */

import { useId, useState } from 'react';
import { Pin, Search, Trash2 } from 'lucide-react';

import { libraryRefusal } from '@/components/settings/voice-library/wording';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { FormSection } from '@/components/ui/form-section';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RowActions } from '@/components/ui/row-actions';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useFishPins, type UseFishPins } from '@/hooks/useFishPins';
import { getIntlLocale, type Language } from '@/i18n/settings';
import type { VoiceOption } from '@/types/llm-config';

import {
  DEFAULT_FISHAUDIO_OUTPUT_FORMAT,
  DEFAULT_FISHAUDIO_TRANSPORT,
  FISHAUDIO_LATENCIES,
  FISHAUDIO_OUTPUT_FORMATS,
  FISHAUDIO_TRANSPORTS,
  FISHAUDIO_SPEED_MAX,
  FISHAUDIO_SPEED_MIN,
  FISHAUDIO_VOICE_ID_PATTERN,
  structuredErrorDetail,
  type SetTtsKey,
  type TTSProviderConfig,
} from './configDialogHelpers';

type Translate = (key: string, options?: Record<string, unknown>) => string;

const KEY = 'settings.admin.llmConfig.voiceTts';

/** Fish Audio — container, latency/quality trade-off, transport, speaking rate. */
export function FishAudioTuning({
  providerConfig,
  setKey,
  t,
}: {
  providerConfig: TTSProviderConfig;
  setKey: SetTtsKey;
  t: Translate;
}) {
  // Accessible names = the visible labels (F012), unique per instance.
  const formatLabelId = useId();
  const latencyLabelId = useId();
  const transportLabelId = useId();
  const transportHintId = useId();
  const speedLabelId = useId();
  const speed = providerConfig.speed ?? 1;
  return (
    <>
      <div className="space-y-3">
        <Label id={formatLabelId}>{t(`${KEY}.outputFormat`)}</Label>
        <Select
          value={providerConfig.output_format ?? DEFAULT_FISHAUDIO_OUTPUT_FORMAT}
          onValueChange={value => setKey('output_format', value)}
        >
          <SelectTrigger aria-labelledby={formatLabelId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FISHAUDIO_OUTPUT_FORMATS.map(format => (
              <SelectItem key={format} value={format}>
                {format}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-3">
        <Label id={latencyLabelId}>{t(`${KEY}.latency`)}</Label>
        <Select
          value={providerConfig.latency ?? 'normal'}
          onValueChange={value => setKey('latency', value)}
        >
          <SelectTrigger aria-labelledby={latencyLabelId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FISHAUDIO_LATENCIES.map(latency => (
              <SelectItem key={latency} value={latency}>
                {t(`${KEY}.latencyOptions.${latency}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-3">
        <Label id={transportLabelId}>{t(`${KEY}.transport`)}</Label>
        <Select
          value={providerConfig.transport ?? DEFAULT_FISHAUDIO_TRANSPORT}
          onValueChange={value => setKey('transport', value)}
        >
          <SelectTrigger aria-labelledby={transportLabelId} aria-describedby={transportHintId}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FISHAUDIO_TRANSPORTS.map(transport => (
              <SelectItem key={transport} value={transport}>
                {t(`${KEY}.transportOptions.${transport}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p id={transportHintId} className="text-xs text-muted-foreground">
          {t(`${KEY}.transportHint`)}
        </p>
      </div>
      <div className="space-y-3">
        <Label id={speedLabelId}>{t(`${KEY}.speed`)}</Label>
        <div className="flex items-center gap-3">
          <input
            type="range"
            aria-labelledby={speedLabelId}
            min={FISHAUDIO_SPEED_MIN}
            max={FISHAUDIO_SPEED_MAX}
            step="0.05"
            value={speed}
            onChange={event => setKey('speed', parseFloat(event.target.value))}
            className="flex-1"
          />
          <span className="text-sm font-mono w-12 text-right">{speed.toFixed(2)}x</span>
        </div>
      </div>
    </>
  );
}

/** What a failed lookup says, in the reader's language. */
function lookupFailure(error: Error, t: Translate): string {
  const type = structuredErrorDetail(error)?.type;
  if (type === 'fishaudio_voice_unavailable') return t(`${KEY}.pinnedUnavailable`);
  if (type === 'fishaudio_voice_id_malformed') return t(`${KEY}.pinnedMalformed`);
  return t(`${KEY}.pinnedLookupFailed`);
}

function describe(voice: VoiceOption): string {
  return [voice.label, voice.language].filter(Boolean).join(' · ');
}

/** The lookup of one voice id the administrator typed, before anything is pinned. */
function usePinLookup() {
  const [draft, setDraft] = useState('');
  const [lookupId, setLookupId] = useState<string | null>(null);
  const { data, loading, error } = useApiQuery<VoiceOption>(
    `/admin/voice/fishaudio/voices/${lookupId ?? ''}`,
    { componentName: 'FishPinnedVoices', enabled: lookupId !== null, deps: [lookupId] }
  );
  return {
    draft,
    setDraft: (value: string) => setDraft(value.trim().toLowerCase()),
    malformed: draft !== '' && !FISHAUDIO_VOICE_ID_PATTERN.test(draft),
    loading,
    error: lookupId !== null ? error : null,
    /** The voice read for the id looked up — never a stale answer for another id. */
    candidate: data && data.voice_id === lookupId ? data : null,
    lookup: () => {
      // The guard, not the attribute, refuses the click (aria-disabled keeps focus).
      if (FISHAUDIO_VOICE_ID_PATTERN.test(draft)) setLookupId(draft);
    },
    clear: () => {
      setDraft('');
      setLookupId(null);
    },
  };
}

/** The instance's pins, each named as the catalogue serves it, each removable. */
function PinnedVoiceList({
  pinned,
  voices,
  removing,
  onRemove,
  t,
}: {
  pinned: string[];
  voices: VoiceOption[];
  /** The pin being removed, while the server answers. */
  removing: string | null;
  onRemove: (voiceId: string) => void;
  t: Translate;
}) {
  if (pinned.length === 0) {
    return <p className="text-sm text-muted-foreground">{t(`${KEY}.pinnedEmpty`)}</p>;
  }
  const offered = new Map(
    voices.filter(voice => voice.source === 'pinned').map(voice => [voice.voice_id, voice])
  );
  return (
    <ul className="space-y-2">
      {pinned.map(voiceId => {
        const voice = offered.get(voiceId);
        const label = voice ? describe(voice) : voiceId;
        return (
          <li
            key={voiceId}
            className="flex items-center justify-between gap-2 rounded-md border px-3 py-2"
          >
            <span className="min-w-0 truncate text-sm">
              {label}
              {!voice && (
                <span className="ml-2 text-xs text-muted-foreground">
                  {t(`${KEY}.pinnedNotOffered`)}
                </span>
              )}
            </span>
            <RowActions
              menuLabel={t(`${KEY}.pinnedActions`, { label })}
              actions={[
                {
                  key: 'remove',
                  label: t(`${KEY}.pinnedRemove`, { label }),
                  icon: Trash2,
                  tone: 'destructive',
                  loading: removing === voiceId,
                  onSelect: () => onRemove(voiceId),
                },
              ]}
            />
          </li>
        );
      })}
    </ul>
  );
}

/** The voice read for the typed id: pinned once the right to it is attested. */
function PinCandidate({
  candidate,
  pinned,
  maxPins,
  pinning,
  onPin,
  t,
}: {
  candidate: VoiceOption;
  pinned: string[];
  maxPins: number;
  pinning: boolean;
  onPin: (voiceId: string, attested: boolean) => void;
  t: Translate;
}) {
  const [attested, setAttested] = useState(false);
  const attestationId = useId();
  const full = pinned.length >= maxPins;
  const canPin = attested && !full && !pinning && !pinned.includes(candidate.voice_id);
  return (
    <div className="space-y-3 rounded-md border p-3">
      <p className="text-sm">{t(`${KEY}.pinnedFound`, { label: describe(candidate) })}</p>
      <div className="flex items-start gap-2">
        <Checkbox
          id={attestationId}
          checked={attested}
          onChange={event => setAttested(event.target.checked)}
          className="mt-0.5"
        />
        <Label htmlFor={attestationId} className="text-sm font-normal">
          {t(`${KEY}.pinnedAttestation`)}
        </Label>
      </div>
      <Button
        type="button"
        onClick={() => {
          if (canPin) onPin(candidate.voice_id, attested);
        }}
        aria-disabled={!canPin}
        isLoading={pinning}
      >
        <Pin className="h-4 w-4" aria-hidden="true" />
        {t(`${KEY}.pinnedAdd`)}
      </Button>
      {full && (
        <p className="text-xs text-muted-foreground">{t(`${KEY}.pinnedFull`, { max: maxPins })}</p>
      )}
    </div>
  );
}

/** One act on the shared list at a time, and what the server said when it refused one. */
function usePinActs(pins: UseFishPins, t: Translate, locale: string, onChanged: () => void) {
  const [pending, setPending] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const run = async (voiceId: string, act: () => Promise<void>): Promise<boolean> => {
    if (pending !== null) return false;
    setPending(voiceId);
    setRefusal(null);
    try {
      await act();
      onChanged();
      return true;
    } catch (error) {
      setRefusal(libraryRefusal(error, t, locale));
      return false;
    } finally {
      setPending(null);
    }
  };
  return {
    pending,
    refusal,
    pin: (voiceId: string, attested: boolean) => run(voiceId, () => pins.pin(voiceId, attested)),
    unpin: (voiceId: string) => run(voiceId, () => pins.unpin(voiceId)),
  };
}

/**
 * The public voices the instance pins — ONE list for every voice slot — and the
 * way to pin one after attesting the right to it. Each act is immediate and
 * filed in the admin audit log; the slot's save carries none of it.
 */
export function FishPinnedVoices({
  lng,
  voices,
  onPinsChanged,
  t,
}: {
  lng: Language;
  /** The catalogue the picker holds: a pinned voice it lists is one the vendor serves. */
  voices: VoiceOption[];
  /** A pin or an unpin changed the catalogue: the caller reads it again. */
  onPinsChanged: () => void;
  t: Translate;
}) {
  const pins = useFishPins(true);
  const lookup = usePinLookup();
  const acts = usePinActs(pins, t, getIntlLocale(lng), onPinsChanged);
  const pinned = pins.pins?.voice_ids ?? [];
  return (
    <FormSection icon={Pin} title={t(`${KEY}.pinnedTitle`)}>
      <p className="text-xs text-muted-foreground">{t(`${KEY}.pinnedDescription`)}</p>
      {pins.pins ? (
        <PinnedVoiceList
          pinned={pinned}
          voices={voices}
          removing={acts.pending}
          onRemove={voiceId => void acts.unpin(voiceId)}
          t={t}
        />
      ) : pins.error ? (
        <p role="alert" className="text-sm text-destructive">
          {libraryRefusal(pins.error, t, getIntlLocale(lng))}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      )}
      {acts.refusal && (
        <p role="alert" className="text-sm text-destructive">
          {acts.refusal}
        </p>
      )}
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <Input
            label={t(`${KEY}.pinnedVoiceId`)}
            value={lookup.draft}
            onChange={event => lookup.setDraft(event.target.value)}
            placeholder={t(`${KEY}.voiceIdPlaceholder`)}
            error={lookup.malformed ? t(`${KEY}.pinnedMalformed`) : undefined}
            spellCheck={false}
            autoComplete="off"
          />
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={lookup.lookup}
          aria-disabled={lookup.draft === '' || lookup.malformed}
          isLoading={lookup.loading}
        >
          <Search className="h-4 w-4" aria-hidden="true" />
          {t(`${KEY}.pinnedLookup`)}
        </Button>
      </div>
      {lookup.error && (
        <p role="alert" className="text-sm text-destructive">
          {lookupFailure(lookup.error, t)}
        </p>
      )}
      {lookup.candidate && pins.pins && (
        <PinCandidate
          // A new candidate starts with nothing attested.
          key={lookup.candidate.voice_id}
          candidate={lookup.candidate}
          pinned={pinned}
          maxPins={pins.pins.max_pins}
          pinning={acts.pending === lookup.candidate.voice_id}
          onPin={(voiceId, attested) => {
            void acts.pin(voiceId, attested).then(pinnedNow => {
              if (pinnedNow) lookup.clear();
            });
          }}
          t={t}
        />
      )}
    </FormSection>
  );
}
