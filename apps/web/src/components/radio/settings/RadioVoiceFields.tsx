'use client';

/**
 * Who speaks: the station's name (its host says it, the player shows it), its
 * personality (its own, or the chat's) and the voice of each role — the station's
 * team, then the commentators of its debates and discussions. A role left automatic
 * gets a voice the station picks; a voice the engine no longer holds is read the
 * same way. A voice a role may not share — a commentator never sounds like LIA, the
 * anchor or another commentator (`voices_apart`, published because the API refuses
 * it) — is offered greyed out.
 */
import {
  AudioLines,
  MessageSquareQuote,
  Mic,
  MicVocal,
  Podcast,
  Radio,
  type LucideIcon,
} from 'lucide-react';
import { useId, useState } from 'react';

import { Disclosure } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { VoiceLanguageFilter } from '@/components/voice/VoiceLanguageFilter';
import { usePersonality } from '@/hooks/usePersonality';
import { useVoiceLanguageFilter } from '@/hooks/useVoiceLanguageFilter';
import { useTranslation } from '@/i18n/client';
import { voicesTakenFrom, withStationName, withVoice } from '@/lib/radio/preferences';
import type {
  RadioPreferences,
  RadioRole,
  RadioSpeakingRole,
  RadioVoiceOption,
} from '@/lib/radio/types';

import type { RadioFieldsProps } from './fields';

/** Select values that stand for « no choice » (a real id is a UUID or a provider's id). */
const CHAT_PERSONALITY = 'chat';
const AUTOMATIC_VOICE = 'automatic';
const ROLE_ICONS: Record<RadioRole, LucideIcon> = {
  host: Radio,
  anchor: MicVocal,
  expert: AudioLines,
  columnist: Podcast,
};

/**
 * The station's name, saved when the listener leaves the field or presses
 * Enter — never per keystroke, which would save every half-typed name. Empty
 * gives the name the listener's language gives the station, shown as the
 * placeholder. A session keeps the name it started with.
 */
function StationNameField({ lng, options, preferences, onChange }: RadioFieldsProps) {
  const { t } = useTranslation(lng);
  const hintId = useId();
  const stored = preferences.station_name ?? '';
  const [draft, setDraft] = useState(stored);
  // The saved name moved under the field (a refused save rolled back): the
  // field follows it — adjusted during render, never in an effect.
  const [shown, setShown] = useState(stored);
  if (shown !== stored) {
    setShown(stored);
    setDraft(stored);
  }
  const commit = () => {
    const next = withStationName(preferences, draft, options.station_name_max_chars);
    setDraft(next.station_name ?? '');
    onChange(next); // the same object when the name did not change: nothing is saved
  };
  const defaultName = t('radio.station_name');
  return (
    <div className="space-y-2">
      <Input
        label={t('radio.settings.voices.station_name')}
        value={draft}
        maxLength={options.station_name_max_chars}
        placeholder={defaultName}
        aria-describedby={hintId}
        onChange={event => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={event => {
          // The Enter that picks an input method's candidate is not the listener's.
          if (event.key !== 'Enter' || event.nativeEvent.isComposing) return;
          event.preventDefault();
          commit();
        }}
      />
      <p id={hintId} className="text-xs text-muted-foreground">
        {t('radio.settings.voices.station_name_hint', { name: defaultName })}
      </p>
    </div>
  );
}

/** One role's voice: « automatic », or a voice of the engine — those it may not share greyed out. */
function VoiceSelect({
  lng,
  role,
  icon: Icon,
  voices,
  preferences,
  taken,
  describedBy,
  onChange,
}: {
  lng: RadioFieldsProps['lng'];
  role: RadioSpeakingRole;
  icon: LucideIcon;
  voices: RadioVoiceOption[];
  preferences: RadioPreferences;
  taken: ReadonlySet<string>;
  describedBy?: string;
  onChange: (next: RadioPreferences) => void;
}) {
  const { t } = useTranslation(lng);
  const id = `radio-voice-${role}`;
  return (
    <div className="space-y-3 rounded-lg border p-4">
      <Label htmlFor={id} className="flex items-center gap-2">
        <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
        {t(`radio.roles.${role}`)}
      </Label>
      <Select
        value={preferences.voices[role] ?? AUTOMATIC_VOICE}
        onValueChange={value =>
          onChange(withVoice(preferences, role, value === AUTOMATIC_VOICE ? null : value))
        }
      >
        <SelectTrigger id={id} className="w-full" aria-describedby={describedBy}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={AUTOMATIC_VOICE}>{t('radio.settings.voices.automatic')}</SelectItem>
          {voices.map(voice => (
            <SelectItem
              key={voice.voice_id}
              value={voice.voice_id}
              disabled={taken.has(voice.voice_id)}
            >
              {voice.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function RadioVoiceFields({ lng, options, preferences, onChange }: RadioFieldsProps) {
  const { t } = useTranslation(lng);
  const commentatorsHintId = useId();
  const { personalities } = usePersonality();
  // The listener's language narrows what each role's list SHOWS; a voice a role
  // holds always stays, and « automatic » is never filtered.
  const language = useVoiceLanguageFilter(options.voices, lng, Object.values(preferences.voices));
  const commentators = options.commentator_roles;
  // A role that may not share a voice (LIA, the anchor, a commentator) is told why a
  // voice of its list is greyed out — by the commentators' own hint.
  const voiceOf = (role: RadioSpeakingRole, icon: LucideIcon) => (
    <VoiceSelect
      key={role}
      lng={lng}
      role={role}
      icon={icon}
      voices={language.shown}
      preferences={preferences}
      taken={voicesTakenFrom(preferences, options.voices_apart, role)}
      describedBy={
        commentators.length > 0 && (options.voices_apart[role]?.length ?? 0) > 0
          ? commentatorsHintId
          : undefined
      }
      onChange={onChange}
    />
  );
  return (
    <Disclosure
      icon={Mic}
      title={t('radio.settings.voices.title')}
      description={t('radio.settings.voices.description')}
    >
      <div className="space-y-4">
        <StationNameField
          lng={lng}
          options={options}
          preferences={preferences}
          onChange={onChange}
        />
        <div className="space-y-3">
          <Label htmlFor="radio-personality">{t('radio.settings.voices.personality')}</Label>
          <Select
            value={preferences.personality_id ?? CHAT_PERSONALITY}
            onValueChange={value =>
              onChange({
                ...preferences,
                personality_id: value === CHAT_PERSONALITY ? null : value,
              })
            }
          >
            <SelectTrigger id="radio-personality" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={CHAT_PERSONALITY}>
                {t('radio.settings.voices.personality_chat')}
              </SelectItem>
              {personalities.map(personality => (
                <SelectItem key={personality.id} value={personality.id}>
                  {`${personality.emoji} ${personality.title}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {language.narrows && (
          <VoiceLanguageFilter lng={lng} only={language.only} onOnlyChange={language.setOnly} />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {options.roles.map(role => voiceOf(role, ROLE_ICONS[role]))}
        </div>
        {commentators.length > 0 && (
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-foreground">
              {t('radio.settings.voices.commentators')}
            </legend>
            <p id={commentatorsHintId} className="text-xs text-muted-foreground">
              {t('radio.settings.voices.commentators_hint')}
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {commentators.map(role => voiceOf(role, MessageSquareQuote))}
            </div>
          </fieldset>
        )}
      </div>
    </Disclosure>
  );
}
