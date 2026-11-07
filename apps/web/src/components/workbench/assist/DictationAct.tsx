'use client';

/**
 * DictationAct — words said into a field (ADR-372).
 *
 * It stands where the field's icon stood, at its size, while the microphone listens: a press ends
 * it, the words join the field and the icon comes back. This component exists only once the person
 * pressed: the chat's own recorder (`useVoiceInput`) opens a connection as soon as it is mounted, and
 * a form must not hold one for nothing. Speech is billed by the server where a remote engine hears
 * it; what it cost is said.
 */
import { Loader2, Square } from 'lucide-react';
import { useEffect, useEffectEvent, useRef } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useVoiceInput } from '@/hooks/useVoiceInput';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatEuro } from '@/lib/format';

export interface DictationActProps {
  lng: Language;
  /** It stands in a field's label line. */
  compact?: boolean;
  /** The words said. */
  onWords: (words: string) => void;
  /** It is over, whatever became of it. */
  onEnd: () => void;
}

export function DictationAct({ lng, compact = false, onWords, onEnd }: DictationActProps) {
  const { t } = useTranslation(lng);
  // Read at the answer: the field may have changed while the person spoke.
  const latest = useRef({ onWords, onEnd });
  useEffect(() => {
    latest.current = { onWords, onEnd };
  });
  const { isRecording, stopRecording, startRecording } = useVoiceInput({
    onTranscription: (text, meta) => {
      const words = text.trim();
      if (words) latest.current.onWords(words);
      else toast.info(t('workbench.assist.voice.nothing_heard'));
      if (meta?.stt_cost_eur) {
        const cost = formatEuro(meta.stt_cost_eur, 6, lng);
        toast(t('workbench.assist.voice.spent', { cost }));
      }
      latest.current.onEnd();
    },
    onError: () => {
      toast.error(t('workbench.assist.voice.dictation_failed'));
      latest.current.onEnd();
    },
  });
  const opening = useEffectEvent(() => void startRecording());
  useEffect(() => {
    // After Strict Mode's second mount: the first would have its microphone closed under it.
    const timer = window.setTimeout(opening, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const label = t('workbench.assist.voice.stop_dictation');
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={compact ? '-my-2 h-8 w-8' : undefined}
      aria-label={label}
      aria-busy={!isRecording || undefined}
      title={label}
      onClick={() => isRecording && stopRecording()}
    >
      {isRecording ? (
        <Square className="h-4 w-4 fill-destructive text-destructive" aria-hidden="true" />
      ) : (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      )}
    </Button>
  );
}
