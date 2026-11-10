'use client';

/**
 * SentenceAssist — a form filled from one sentence (ADR-372).
 *
 * The form is the review, so the answer goes straight to it and nothing else is shown: nothing
 * exists until the person saves it. A refusal keeps their words, and what the sentence cost stays
 * beside the icon. Inside a form its own submit stops at itself (`InstructionForm`), and the
 * sentence may be dictated where the instance offers it. `SentenceDialog` is the asking alone, for
 * a screen that offers it among other ways (a new contact's « Write with LIA »).
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import type { Language } from '@/i18n/settings';
import type { AssistAnswer } from '@/lib/workbench/assist';
import type { LLMUsage } from '@/types/llm-usage';

import { AssistStars } from '@/components/selection-assist/AssistStars';
import { useAssistCall } from '@/hooks/useAssistCall';
import { InstructionForm, WaitOrRefusal } from './WritingAssist';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

export interface SentenceDialogProps<A extends AssistAnswer> {
  lng: Language;
  /** What the dialog is called. */
  label: string;
  /** Where it asks. */
  path: string;
  /** The longest sentence the routes take. */
  maxInstruction: number | undefined;
  /** What goes with the sentence. */
  body?: object;
  /** The sentence, kept by the caller: a refusal or a closing keeps it for the next try. */
  words: string;
  onWords: (words: string) => void;
  onAnswer: (answer: A) => void;
  onClose: () => void;
}

/** The asking: the sentence, then the answer handed over and the dialog closed. */
export function SentenceDialog<A extends AssistAnswer>({
  lng,
  label,
  path,
  maxInstruction,
  body = {},
  words,
  onWords,
  onAnswer,
  onClose,
}: SentenceDialogProps<A>) {
  const call = useAssistCall<A>();
  const leave = () => {
    call.stop();
    onClose();
  };
  const ask = async () => {
    const answer = await call.run(path, { sentence: words.trim(), ...body });
    if (!answer) return;
    onAnswer(answer);
    leave();
  };
  return (
    <Dialog open onOpenChange={next => !next && leave()}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-lg">
        <ToolDialogHeader>
          <DialogTitle>{label}</DialogTitle>
        </ToolDialogHeader>
        <InstructionForm
          lng={lng}
          required
          words={words}
          maxLength={maxInstruction}
          running={call.state.status === 'running'}
          onWords={onWords}
          onAsk={() => void ask()}
        />
        <WaitOrRefusal lng={lng} state={call.state} />
        <ToolActions>
          <CancelButton lng={lng} onClick={leave} />
        </ToolActions>
      </DialogContent>
    </Dialog>
  );
}

export interface SentenceAssistProps<A extends AssistAnswer> {
  lng: Language;
  /** What the icon and the dialog are called. */
  label: string;
  /** Where it asks. */
  path: string;
  /** The longest sentence the routes take. */
  maxInstruction: number | undefined;
  /** What goes with the sentence. */
  body?: object;
  onAnswer: (answer: A) => void;
}

export function SentenceAssist<A extends AssistAnswer>({
  lng,
  label,
  path,
  maxInstruction,
  body,
  onAnswer,
}: SentenceAssistProps<A>) {
  const [open, setOpen] = useState(false);
  const [words, setWords] = useState('');
  const [usage, setUsage] = useState<LLMUsage | null>(null);
  return (
    <span className="inline-flex items-center gap-1">
      {usage && <LLMUsageBadge usage={usage} />}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        aria-label={label}
        title={label}
        onClick={() => setOpen(true)}
      >
        <AssistStars className="h-4 w-4" aria-hidden="true" />
      </Button>
      {open && (
        <SentenceDialog<A>
          lng={lng}
          label={label}
          path={path}
          maxInstruction={maxInstruction}
          body={body}
          words={words}
          onWords={setWords}
          onAnswer={answer => {
            onAnswer(answer);
            setUsage(answer.usage);
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </span>
  );
}
