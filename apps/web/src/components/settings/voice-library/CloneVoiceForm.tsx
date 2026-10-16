'use client';

/**
 * Clone a voice from recordings (ADR-345). The administrator attests the voice
 * is theirs, or that its owner consented in writing — the attestation is filed
 * in the admin audit log before anything reaches the vendor, and the voice is
 * private to the account. Every bound the form checks is the one the API
 * publishes and enforces; the local engine can fill a recording's transcript
 * when the instance runs it.
 */

import { type FormEvent, useId, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { Copy, FileAudio, Trash2, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { FormSection } from '@/components/ui/form-section';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { formatFileSize } from '@/lib/utils/image-compress';
import type {
  CloneRequest,
  LibraryLanguage,
  LibraryVoice,
  VoiceLibraryBounds,
} from '@/types/voice-library';

import { LanguageSelect } from './LanguageSelect';
import { libraryRefusal } from './wording';

const KEY = 'settings.admin.voiceLibrary.clone';

interface Sample {
  id: number;
  file: File;
  text: string;
}

function extensionOf(file: File): string {
  const dot = file.name.lastIndexOf('.');
  return dot >= 0 ? file.name.slice(dot + 1).toLowerCase() : '';
}

/** Why the form cannot be sent yet — the API's own bounds — or `null`. */
function cloneProblem(
  title: string,
  samples: readonly Sample[],
  consent: boolean,
  bounds: VoiceLibraryBounds,
  t: TFunction
): string | null {
  if (!title.trim()) return t(`${KEY}.problems.title`);
  if (samples.length === 0) return t(`${KEY}.problems.noSample`);
  if (samples.length > bounds.samples_max) {
    return t(`${KEY}.problems.tooMany`, { max: bounds.samples_max });
  }
  if (samples.some(sample => !bounds.sample_extensions.includes(extensionOf(sample.file)))) {
    return t(`${KEY}.problems.format`, { formats: bounds.sample_extensions.join(', ') });
  }
  const total = samples.reduce((sum, sample) => sum + sample.file.size, 0);
  if (
    samples.some(sample => sample.file.size > bounds.sample_max_bytes) ||
    total > bounds.total_max_bytes
  ) {
    return t(`${KEY}.problems.size`, {
      perFile: formatFileSize(bounds.sample_max_bytes),
      total: formatFileSize(bounds.total_max_bytes),
    });
  }
  const written = samples.filter(sample => sample.text.trim()).length;
  if (written > 0 && written < samples.length) return t(`${KEY}.problems.texts`);
  if (!consent) return t(`${KEY}.problems.consent`);
  return null;
}

interface SampleRowProps {
  sample: Sample;
  index: number;
  canPrefill: boolean;
  prefilling: boolean;
  t: TFunction;
  onText: (text: string) => void;
  onPrefill: () => void;
  onRemove: () => void;
}

function SampleRow({
  sample,
  index,
  canPrefill,
  prefilling,
  t,
  onText,
  onPrefill,
  onRemove,
}: SampleRowProps) {
  return (
    <li className="space-y-3 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="flex min-w-0 items-center gap-2 text-sm">
          <FileAudio className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="truncate">{sample.file.name}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {formatFileSize(sample.file.size)}
          </span>
        </p>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="text-destructive"
          aria-label={t(`${KEY}.removeSample`, { name: sample.file.name })}
          onClick={onRemove}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <Textarea
        label={t(`${KEY}.transcriptLabel`, { index })}
        value={sample.text}
        rows={2}
        onChange={event => onText(event.target.value)}
      />
      {canPrefill && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          isLoading={prefilling}
          aria-disabled={prefilling}
          onClick={onPrefill}
        >
          <Wand2 className="h-4 w-4" aria-hidden="true" />
          {t(`${KEY}.prefill`)}
        </Button>
      )}
    </li>
  );
}

export interface CloneVoiceFormProps {
  bounds: VoiceLibraryBounds;
  /** The Intl locale a refusal's list is joined in. */
  locale: string;
  prefillAvailable: boolean;
  t: TFunction;
  onClone: (request: CloneRequest) => Promise<LibraryVoice>;
  onTranscribe: (sample: File, language: LibraryLanguage | null) => Promise<string>;
}

export function CloneVoiceForm({
  bounds,
  locale,
  prefillAvailable,
  t,
  onClone,
  onTranscribe,
}: CloneVoiceFormProps) {
  const consentId = useId();
  const enhanceId = useId();
  const nextId = useRef(0);
  const [title, setTitle] = useState('');
  const [samples, setSamples] = useState<Sample[]>([]);
  const [language, setLanguage] = useState<LibraryLanguage | null>(null);
  const [enhance, setEnhance] = useState(true);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prefilling, setPrefilling] = useState<number | null>(null);
  const problem = cloneProblem(title, samples, consent, bounds, t);

  const add = (files: FileList | null) => {
    const picked = Array.from(files ?? []).map(file => ({ id: nextId.current++, file, text: '' }));
    setSamples(current => [...current, ...picked]);
  };
  const update = (id: number, text: string) =>
    setSamples(current => current.map(sample => (sample.id === id ? { ...sample, text } : sample)));

  const prefill = async (sample: Sample) => {
    if (prefilling !== null) return;
    setPrefilling(sample.id);
    try {
      update(sample.id, await onTranscribe(sample.file, language));
    } catch (error) {
      toast.error(libraryRefusal(error, t, locale));
    } finally {
      setPrefilling(null);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (problem) {
      toast.error(problem);
      return;
    }
    setBusy(true);
    try {
      const voice = await onClone({
        title: title.trim(),
        samples: samples.map(sample => sample.file),
        texts: samples.map(sample => sample.text),
        enhanceAudioQuality: enhance,
        consent,
      });
      toast.success(t(`${KEY}.cloned`, { title: voice.title }));
      setTitle('');
      setSamples([]);
      setConsent(false);
    } catch (error) {
      toast.error(libraryRefusal(error, t, locale));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-busy={busy}>
      <FormSection icon={Copy} title={t(`${KEY}.title`)}>
        <p className="text-sm text-muted-foreground">{t(`${KEY}.help`)}</p>
        <Input
          label={t(`${KEY}.nameLabel`)}
          value={title}
          maxLength={bounds.title_max_chars}
          onChange={event => setTitle(event.target.value)}
        />
        <div className="space-y-3">
          <Input
            type="file"
            multiple
            label={t(`${KEY}.samplesLabel`)}
            accept={bounds.sample_extensions.map(extension => `.${extension}`).join(',')}
            onChange={event => {
              add(event.target.files);
              event.target.value = '';
            }}
          />
          <p className="text-xs text-muted-foreground">
            {t(`${KEY}.samplesHelp`, {
              formats: bounds.sample_extensions.join(', '),
              max: bounds.samples_max,
              perFile: formatFileSize(bounds.sample_max_bytes),
              total: formatFileSize(bounds.total_max_bytes),
            })}
          </p>
        </div>
        {samples.length > 0 && (
          <>
            <p className="text-xs text-muted-foreground">{t(`${KEY}.transcriptHelp`)}</p>
            {prefillAvailable && (
              <LanguageSelect
                label={t(`${KEY}.languageLabel`)}
                autoLabel={t(`${KEY}.languageAuto`)}
                value={language}
                onChange={setLanguage}
              />
            )}
            <ul className="space-y-3">
              {samples.map((sample, index) => (
                <SampleRow
                  key={sample.id}
                  sample={sample}
                  index={index + 1}
                  canPrefill={prefillAvailable}
                  prefilling={prefilling === sample.id}
                  t={t}
                  onText={text => update(sample.id, text)}
                  onPrefill={() => void prefill(sample)}
                  onRemove={() =>
                    setSamples(current => current.filter(item => item.id !== sample.id))
                  }
                />
              ))}
            </ul>
          </>
        )}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <Label htmlFor={enhanceId}>{t(`${KEY}.enhanceLabel`)}</Label>
            <p id={`${enhanceId}-help`} className="text-xs text-muted-foreground">
              {t(`${KEY}.enhanceHelp`)}
            </p>
          </div>
          <Switch
            id={enhanceId}
            checked={enhance}
            aria-describedby={`${enhanceId}-help`}
            onCheckedChange={setEnhance}
          />
        </div>
        <div className="flex items-start gap-3">
          <Checkbox
            id={consentId}
            checked={consent}
            aria-describedby={`${consentId}-help`}
            onChange={event => setConsent(event.target.checked)}
            className="mt-0.5"
          />
          <div className="space-y-1">
            <Label htmlFor={consentId}>{t(`${KEY}.consentLabel`)}</Label>
            <p id={`${consentId}-help`} className="text-xs text-muted-foreground">
              {t(`${KEY}.consentHelp`)}
            </p>
          </div>
        </div>
        <div className="space-y-2">
          <Button type="submit" isLoading={busy} aria-disabled={busy || problem !== null}>
            {t(`${KEY}.submit`)}
          </Button>
          {problem && samples.length > 0 && (
            <p className="text-xs text-muted-foreground">{problem}</p>
          )}
        </div>
      </FormSection>
    </form>
  );
}
