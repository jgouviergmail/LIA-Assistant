'use client';

/**
 * SentenceAssist — a form filled from one sentence (ADR-372).
 *
 * The form is the review, so the answer goes straight to it and nothing else is shown: nothing
 * exists until the person saves it. A refusal keeps their words, and what the sentence cost stays
 * beside the icon. Inside a form its own submit stops at itself (`InstructionForm`).
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import type { Language } from '@/i18n/settings';
import type { AssistAnswer } from '@/lib/workbench/assist';
import type { LLMUsage } from '@/types/llm-usage';

import { AssistStars } from './AssistStars';
import { useAssistCall } from './useAssistCall';
import { InstructionForm, WaitOrRefusal } from './WritingAssist';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

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
  body = {},
  onAnswer,
}: SentenceAssistProps<A>) {
  const [open, setOpen] = useState(false);
  const [words, setWords] = useState('');
  const [usage, setUsage] = useState<LLMUsage | null>(null);
  const call = useAssistCall<A>();
  const leave = () => {
    call.stop();
    setOpen(false);
  };
  const ask = async () => {
    const answer = await call.run(path, { sentence: words.trim(), ...body });
    if (!answer) return;
    onAnswer(answer);
    setUsage(answer.usage);
    leave();
  };
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
              onWords={setWords}
              onAsk={() => void ask()}
            />
            <WaitOrRefusal lng={lng} state={call.state} />
            <ToolActions>
              <CancelButton lng={lng} onClick={leave} />
            </ToolActions>
          </DialogContent>
        </Dialog>
      )}
    </span>
  );
}
