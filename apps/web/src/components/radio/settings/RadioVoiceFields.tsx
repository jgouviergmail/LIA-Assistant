'use client';

/**
 * Who speaks: the station's name (its host says it, the player shows it), its
 * personality (its own, or the chat's) and the voice of each role. A role left
 * automatic gets a voice the station picks, alternating genders; a voice the
 * engine no longer holds is read the same way.
 */
import { AudioLines, Mic, MicVocal, Podcast, Radio, type LucideIcon } from 'lucide-react';
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
import { usePersonality } from '@/hooks/usePersonality';
import { useTranslation } from '@/i18n/client';
import { withStationName, withVoice } from '@/lib/radio/preferences';
import type { RadioRole } from '@/lib/radio/types';

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

export function RadioVoiceFields({ lng, options, preferences, onChange }: RadioFieldsProps) {
  const { t } = useTranslation(lng);
  const { personalities } = usePersonality();
  const voiceFor = (role: RadioRole) => (value: string) =>
    onChange(withVoice(preferences, role, value === AUTOMATIC_VOICE ? null : value));
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
        <div className="grid gap-4 sm:grid-cols-2">
          {options.roles.map(role => {
            const Icon = ROLE_ICONS[role];
            const id = `radio-voice-${role}`;
            return (
              <div key={role} className="space-y-3 rounded-lg border p-4">
                <Label htmlFor={id} className="flex items-center gap-2">
                  <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
                  {t(`radio.roles.${role}`)}
                </Label>
                <Select
                  value={preferences.voices[role] ?? AUTOMATIC_VOICE}
                  onValueChange={voiceFor(role)}
                >
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={AUTOMATIC_VOICE}>
                      {t('radio.settings.voices.automatic')}
                    </SelectItem>
                    {options.voices.map(voice => (
                      <SelectItem key={voice.voice_id} value={voice.voice_id}>
                        {voice.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>
      </div>
    </Disclosure>
  );
}
