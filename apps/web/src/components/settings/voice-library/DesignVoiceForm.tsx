'use client';

/**
 * Design voices from a description (ADR-345). The instance pays one request
 * whatever the number of candidates — the form says how much before it is
 * sent — and the candidates wait server-side: saving one names it, the
 * administrator having listened to it first.
 */

import { type FormEvent, useId, useState } from 'react';
import type { TFunction } from 'i18next';
import { Check, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { FormSection } from '@/components/ui/form-section';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type {
  DesignCandidate,
  DesignRequest,
  DesignResult,
  LibraryLanguage,
  LibraryVoice,
  VoiceLibraryBounds,
} from '@/types/voice-library';

import { LanguageSelect } from './LanguageSelect';
import { libraryRefusal } from './wording';

const KEY = 'settings.admin.voiceLibrary.design';

interface CandidateCardProps {
  candidate: DesignCandidate;
  index: number;
  maxChars: number;
  saved: boolean;
  t: TFunction;
  onSave: (title: string) => Promise<void>;
}

function CandidateCard({ candidate, index, maxChars, saved, t, onSave }: CandidateCardProps) {
  const [title, setTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const label = t(`${KEY}.candidate`, { index });
  const words = title.trim();

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || saved || !words) return;
    setSaving(true);
    try {
      await onSave(words);
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className="space-y-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
        {label}
        <span className="text-xs font-normal text-muted-foreground">
          {t(`${KEY}.duration`, { seconds: (candidate.duration_ms / 1000).toFixed(1) })}
        </span>
      </div>
      {/* A data: URL — the page's own bytes, no object URL to revoke (CSP media-src data:). */}
      <audio
        controls
        preload="none"
        aria-label={label}
        className="w-full"
        src={`data:audio/wav;base64,${candidate.audio_base64}`}
      />
      {candidate.text && (
        <p className="text-xs text-muted-foreground">
          {t(`${KEY}.quote`, { text: candidate.text })}
        </p>
      )}
      {saved ? (
        <Badge variant="success">
          <Check className="h-3 w-3" aria-hidden="true" />
          {t(`${KEY}.saved`)}
        </Badge>
      ) : (
        <form onSubmit={save} className="space-y-3">
          <Input
            label={t(`${KEY}.nameLabel`, { index })}
            value={title}
            maxLength={maxChars}
            onChange={event => setTitle(event.target.value)}
          />
          <Button type="submit" size="sm" isLoading={saving} aria-disabled={saving || !words}>
            {t(`${KEY}.save`)}
          </Button>
        </form>
      )}
    </li>
  );
}

export interface DesignVoiceFormProps {
  /** The Intl locale the price is written in. */
  locale: string;
  bounds: VoiceLibraryBounds;
  costUsd: number;
  t: TFunction;
  onDesign: (request: DesignRequest) => Promise<DesignResult>;
  onSave: (candidateId: string, title: string) => Promise<LibraryVoice>;
}

export function DesignVoiceForm({
  locale,
  bounds,
  costUsd,
  t,
  onDesign,
  onSave,
}: DesignVoiceFormProps) {
  const countId = useId();
  const [instruction, setInstruction] = useState('');
  const [preview, setPreview] = useState('');
  const [language, setLanguage] = useState<LibraryLanguage | null>(null);
  const [count, setCount] = useState(Math.min(2, bounds.candidates_max));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DesignResult | null>(null);
  const [saved, setSaved] = useState<ReadonlySet<string>>(new Set());
  const cost = new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(
    costUsd
  );
  const described = instruction.trim().length > 0;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !described) return;
    setBusy(true);
    try {
      setResult(
        await onDesign({
          instruction: instruction.trim(),
          preview_text: preview.trim() || null,
          language,
          count,
        })
      );
      setSaved(new Set());
    } catch (error) {
      toast.error(libraryRefusal(error, t, locale));
    } finally {
      setBusy(false);
    }
  };

  const save = async (candidateId: string, title: string) => {
    try {
      const voice = await onSave(candidateId, title);
      setSaved(current => new Set([...current, candidateId]));
      toast.success(t(`${KEY}.savedToast`, { title: voice.title }));
    } catch (error) {
      toast.error(libraryRefusal(error, t, locale));
    }
  };

  return (
    <div className="space-y-4">
      <form onSubmit={submit} aria-busy={busy}>
        <FormSection icon={Sparkles} title={t(`${KEY}.title`)}>
          <p className="text-sm text-muted-foreground">{t(`${KEY}.help`)}</p>
          <Textarea
            label={t(`${KEY}.instructionLabel`)}
            placeholder={t(`${KEY}.instructionPlaceholder`)}
            value={instruction}
            rows={3}
            maxLength={bounds.instruction_max_chars}
            onChange={event => setInstruction(event.target.value)}
          />
          <Input
            label={t(`${KEY}.previewLabel`)}
            value={preview}
            maxLength={bounds.preview_max_chars}
            onChange={event => setPreview(event.target.value)}
          />
          <LanguageSelect
            label={t(`${KEY}.languageLabel`)}
            autoLabel={t(`${KEY}.languageAuto`)}
            value={language}
            onChange={setLanguage}
          />
          <div className="space-y-3">
            <Label id={countId}>{t(`${KEY}.countLabel`)}</Label>
            <Select value={String(count)} onValueChange={value => setCount(Number(value))}>
              <SelectTrigger aria-labelledby={countId}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: bounds.candidates_max }, (_, index) => index + 1).map(n => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">{t(`${KEY}.cost`, { cost })}</p>
          <Button type="submit" isLoading={busy} aria-disabled={busy || !described}>
            {t(`${KEY}.submit`)}
          </Button>
        </FormSection>
      </form>
      {result && (
        <section className="space-y-3" aria-label={t(`${KEY}.candidatesTitle`)}>
          <p className="text-xs text-muted-foreground">
            {t(`${KEY}.expires`, { minutes: Math.round(result.expires_in_seconds / 60) })}
          </p>
          <ul className="space-y-3">
            {result.candidates.map((candidate, index) => (
              <CandidateCard
                key={candidate.candidate_id}
                candidate={candidate}
                index={index + 1}
                maxChars={bounds.title_max_chars}
                saved={saved.has(candidate.candidate_id)}
                t={t}
                onSave={title => save(candidate.candidate_id, title)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
