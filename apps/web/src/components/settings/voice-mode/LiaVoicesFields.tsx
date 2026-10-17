'use client';

/**
 * LIA's voices — the male and the female voice LIA speaks with in the chat, the
 * person's own or the administrator's (ADR-345 amendment 2026-10-14).
 *
 * The lists hold the voices of the engine that speaks, as `GET /voice/lia-voices`
 * publishes them (the person's language rule applied, native voices first),
 * narrowed by the switch every voice picker shares; each opens on the
 * administrator's voice, named. A change is saved at once and nothing is
 * disabled meanwhile — a keyboard user keeps their place — so every save sends
 * the latest choice of BOTH genders: a quick second change never undoes the
 * first. A refused save says why; the lists keep what the server holds.
 */

import { MicVocal } from 'lucide-react';
import { useId, useRef } from 'react';
import { toast } from 'sonner';

import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { VoiceLanguageFilter } from '@/components/voice/VoiceLanguageFilter';
import { VoiceSamplePlayback } from '@/components/voice/VoiceSamplePlayback';
import { useLiaVoices } from '@/hooks/useLiaVoices';
import { useTtsVoiceSample } from '@/hooks/useTtsVoiceSample';
import { useVoiceLanguageFilter } from '@/hooks/useVoiceLanguageFilter';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { getApiErrorFields } from '@/lib/api-error';
import type { Translate } from '@/lib/batch-report';
import {
  LIA_VOICE_GENDERS,
  type LiaVoiceChoice,
  type LiaVoiceGender,
  type LiaVoices,
} from '@/types/lia-voices';
import type { VoiceOption } from '@/types/llm-config';

const KEY = 'settings.voice_mode.lia_voices';

/** The select value standing for « the administrator's voice » (no provider id reads so). */
const DEFAULT_VOICE = 'default';

/** What a refused save says, in the reader's language. */
function refusalOf(error: unknown, t: Translate): string {
  const code = getApiErrorFields(error)?.code;
  return code === 'lia_voice_unknown' || code === 'lia_voice_catalogue_unavailable'
    ? t(`${KEY}.errors.${code}`)
    : t('common.error');
}

function defaultOf(lia: LiaVoices, gender: LiaVoiceGender): VoiceOption {
  return gender === 'male' ? lia.default_male : lia.default_female;
}

/** One gender's list: its voices and those that name no gender, after the default. */
function LiaVoicePicker({
  gender,
  value,
  fallback,
  voices,
  onChange,
  t,
}: {
  gender: LiaVoiceGender;
  value: string | null;
  fallback: VoiceOption;
  voices: VoiceOption[];
  onChange: (value: string) => void;
  t: Translate;
}) {
  const id = useId();
  const listed = voices.filter(voice => voice.gender === gender || voice.gender === null);
  // A voice held while the engine cannot list its voices stays shown, by its id.
  const held =
    value !== null && !listed.some(voice => voice.voice_id === value)
      ? [{ voice_id: value, label: value, gender, language: null }]
      : [];
  const options = [...held, ...listed];
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{t(`${KEY}.${gender}`)}</Label>
      <Select value={value ?? DEFAULT_VOICE} onValueChange={onChange}>
        <SelectTrigger id={id} className="w-full bg-card">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_VOICE}>
            {t(`${KEY}.default`, { name: fallback.label })}
          </SelectItem>
          {options.map(voice => (
            <SelectItem key={voice.voice_id} value={voice.voice_id}>
              {voice.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function LiaVoicesBlock({
  lng,
  lia,
  save,
}: {
  lng: Language;
  lia: LiaVoices;
  save: (choice: LiaVoiceChoice) => Promise<void>;
}) {
  const { t } = useTranslation(lng);
  const titleId = useId();
  const sample = useTtsVoiceSample();
  // The latest choice asked for while a save is in flight; null once settled.
  const requested = useRef<LiaVoiceChoice | null>(null);
  const language = useVoiceLanguageFilter(lia.voices, lng, [lia.male, lia.female]);
  const choose = (gender: LiaVoiceGender) => (value: string) => {
    const base = requested.current ?? { male: lia.male, female: lia.female };
    const next = { ...base, [gender]: value === DEFAULT_VOICE ? null : value };
    requested.current = next;
    void sample.play({
      endpoint: '/voice/lia-voices/sample',
      payload: { gender, voice_id: next[gender] },
    });
    void save(next)
      .then(() => toast.success(t(`${KEY}.saved`)))
      .catch(error => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        toast.error(refusalOf(error, t));
      })
      .finally(() => {
        if (requested.current === next) requested.current = null;
      });
  };
  return (
    <div
      role="group"
      aria-labelledby={titleId}
      className="space-y-3 rounded-lg border bg-background p-3"
    >
      <p id={titleId} className="flex items-center gap-2 text-sm font-medium">
        <MicVocal className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`${KEY}.title`)}
      </p>
      <p className="text-xs text-muted-foreground">{t(`${KEY}.description`)}</p>
      {language.narrows && (
        <VoiceLanguageFilter lng={lng} only={language.only} onOnlyChange={language.setOnly} />
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {LIA_VOICE_GENDERS.map(gender => (
          <LiaVoicePicker
            key={gender}
            gender={gender}
            value={lia[gender]}
            fallback={defaultOf(lia, gender)}
            voices={language.shown}
            onChange={choose(gender)}
            t={t}
          />
        ))}
      </div>
      <VoiceSamplePlayback lng={lng} sample={sample} />
    </div>
  );
}

/** The block in the voice mode settings — nothing at all where LIA does not speak. */
export function LiaVoicesFields({ lng }: { lng: Language }) {
  const { t } = useTranslation(lng);
  const { lia, loading, error, save } = useLiaVoices();
  if (!lia) {
    if (loading) return <Skeleton className="h-28 w-full" />;
    return error ? (
      <p className="text-xs text-muted-foreground">{t(`${KEY}.unavailable`)}</p>
    ) : null;
  }
  if (!lia.available) return null;
  return <LiaVoicesBlock lng={lng} lia={lia} save={save} />;
}
