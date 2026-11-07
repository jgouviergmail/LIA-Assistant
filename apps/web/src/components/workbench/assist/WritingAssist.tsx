'use client';

/**
 * WritingAssist — writing with LIA beside a field (ADR-372).
 *
 * One icon in a line the field already has, so a form on a phone gains no height; the list opens
 * under it. A line that needs the person's words asks for them; every line ends on a proposal,
 * shown apart, that changes nothing until they say so: words already written are replaced or added
 * to by their choice alone. Leaving stops what is on its way. A proposal is plain text: what a model
 * wrote never becomes markup here.
 */
import { Mic, type LucideIcon } from 'lucide-react';
import { useEffect, useEffectEvent, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { TextAnswer } from '@/lib/workbench/assist';

import { BarAct } from '../DetailBar';
import { AssistStars } from './AssistStars';
import { DictationAct } from './DictationAct';
import { useAssistCall, type AssistCall, type AssistState } from './useAssistCall';
import { CancelButton, ToolActions, ToolDialogHeader } from '../ToolForm';

/** How a proposal joins what the field holds. */
export type WritingUse = 'replace' | 'add';

/** One thing LIA can write here. */
export interface WritingLine {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Where it asks. */
  path: string;
  /** What it sends, given the person's instruction when it takes one. */
  body: (instruction: string | null) => object;
  /** It takes the person's words first: to be said, or if they wish. */
  instruction?: 'optional' | 'required';
  /** What those words are, where they are not an instruction. */
  instructionLabel?: string;
  /** Words a press puts in the instruction. */
  suggestions?: readonly string[];
  /** Its proposal stands alone: nothing to add it to. */
  whole?: boolean;
}

export interface WritingAssistProps {
  lng: Language;
  lines: readonly WritingLine[];
  /** The field holds nothing of the person's yet. */
  blank: boolean;
  /** The longest instruction the routes take. */
  maxInstruction: number | undefined;
  onApply: (answer: TextAnswer, use: WritingUse, line: WritingLine) => void;
  /** The line it opens on, asked at once: the person already chose it elsewhere. */
  startWith?: string | null;
  /** It stands in a field's label line. */
  compact?: boolean;
  /** Words said join the field; left out where nothing can hear them. */
  onDictated?: (words: string) => void;
}

export function WritingAssist({
  lng,
  lines,
  blank,
  maxInstruction,
  onApply,
  startWith = null,
  compact = false,
  onDictated,
}: WritingAssistProps) {
  const { t } = useTranslation(lng);
  const [open, setOpen] = useState<WritingLine | null>(null);
  const [instruction, setInstruction] = useState('');
  const [dictating, setDictating] = useState(false);
  const call = useAssistCall<TextAnswer>();

  const ask = (line: WritingLine, words: string) => {
    void call.run(line.path, line.body(words.trim() || null));
  };
  const begin = (line: WritingLine) => {
    setOpen(line);
    setInstruction('');
    if (!line.instruction) ask(line, '');
  };
  const leave = () => {
    call.stop();
    setOpen(null);
  };
  const opening = useEffectEvent((key: string) => {
    const line = lines.find(item => item.key === key);
    if (!line) return;
    setOpen(line);
    ask(line, '');
  });
  useEffect(() => {
    if (!startWith) return undefined;
    // After Strict Mode's second mount: a first call would be paid for and thrown away.
    const timer = window.setTimeout(() => opening(startWith), 0);
    return () => window.clearTimeout(timer);
  }, [startWith]);

  if (lines.length === 0 && !onDictated) return null;
  const answer = call.state.status === 'done' ? call.state.value : null;
  if (dictating && onDictated) {
    return (
      <DictationAct
        lng={lng}
        compact={compact}
        onWords={onDictated}
        onEnd={() => setDictating(false)}
      />
    );
  }
  return (
    <>
      <BarAct
        act={{
          label: t('workbench.assist.writing.open'),
          icon: AssistStars,
          busy: call.state.status === 'running',
          compact,
          choices: [
            ...lines.map(line => ({
              label: line.label,
              icon: line.icon,
              onSelect: () => begin(line),
            })),
            ...(onDictated
              ? [
                  {
                    label: t('workbench.assist.voice.dictate'),
                    icon: Mic,
                    ruled: true,
                    onSelect: () => setDictating(true),
                  },
                ]
              : []),
          ],
        }}
      />
      {open && (
        <Dialog open onOpenChange={next => !next && leave()}>
          <DialogContent aria-describedby={undefined} className="sm:max-w-lg">
            <ToolDialogHeader>
              <DialogTitle>{open.label}</DialogTitle>
            </ToolDialogHeader>
            {open.instruction && (
              <InstructionForm
                lng={lng}
                required={open.instruction === 'required'}
                label={open.instructionLabel}
                suggestions={open.suggestions}
                words={instruction}
                maxLength={maxInstruction}
                running={call.state.status === 'running'}
                onWords={setInstruction}
                onAsk={() => ask(open, instruction)}
              />
            )}
            <Proposal lng={lng} call={call} withRetry={!open.instruction} />
            <ToolActions>
              <CancelButton lng={lng} onClick={leave} />
              {answer && (
                <UseButtons
                  lng={lng}
                  single={blank || Boolean(open.whole)}
                  onUse={use => {
                    onApply(answer, use, open);
                    leave();
                  }}
                />
              )}
            </ToolActions>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

/** What the person says the proposal should do, and what a press can say for them. */
export function InstructionForm({
  lng,
  required,
  label: named,
  suggestions,
  words,
  maxLength,
  running,
  onWords,
  onAsk,
}: {
  lng: Language;
  /** Nothing is asked without words. */
  required: boolean;
  /** What the words are, where they are not an instruction. */
  label?: string;
  suggestions?: readonly string[];
  words: string;
  maxLength: number | undefined;
  running: boolean;
  onWords: (words: string) => void;
  onAsk: () => void;
}) {
  const { t } = useTranslation(lng);
  const held = required && !words.trim();
  const label = named ?? t('workbench.assist.writing.instruction');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    // A portal keeps React's tree: this submit would reach the composer's form, and send the mail.
    event.stopPropagation();
    if (!held && !running) onAsk();
  };
  return (
    <form className="space-y-2" onSubmit={submit}>
      <Textarea
        aria-label={label}
        placeholder={label}
        rows={2}
        value={words}
        maxLength={maxLength}
        onChange={event => onWords(event.target.value)}
      />
      <div className="flex flex-wrap items-center gap-1.5">
        {suggestions?.map(suggestion => (
          <Button
            key={suggestion}
            type="button"
            variant="outline"
            size="sm"
            className="h-8 px-2.5 text-xs"
            onClick={() => onWords(suggestion)}
          >
            {suggestion}
          </Button>
        ))}
        <Button
          type="submit"
          size="sm"
          className="ml-auto"
          isLoading={running}
          aria-disabled={held || undefined}
        >
          {t('workbench.assist.writing.ask')}
        </Button>
      </div>
    </form>
  );
}

/** What is on its way, or why nothing came: every dialog that asks shows one or the other. */
export function WaitOrRefusal<T>({
  lng,
  state,
  onRetry,
}: {
  lng: Language;
  state: AssistState<T>;
  /** Asks again; left out where the dialog has its own way to. */
  onRetry?: () => void;
}) {
  const { t } = useTranslation(lng);
  if (state.status === 'running') {
    return (
      <div role="status" className="space-y-2" aria-busy="true">
        <span className="sr-only">{t('workbench.assist.writing.writing')}</span>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }
  if (state.status !== 'failed') return null;
  return (
    <div className="space-y-2 text-sm">
      <p role="alert" className="text-destructive">
        {state.refusal ? t(state.refusal.key, state.refusal.values) : t('workbench.assist.failed')}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t('workbench.states.retry')}
        </Button>
      )}
    </div>
  );
}

/** What is on its way, what came back, or why nothing did. */
function Proposal({
  lng,
  call,
  withRetry,
}: {
  lng: Language;
  call: AssistCall<TextAnswer>;
  withRetry: boolean;
}) {
  const { state } = call;
  if (state.status !== 'done') {
    return (
      <WaitOrRefusal
        lng={lng}
        state={state}
        onRetry={withRetry ? () => void call.retry() : undefined}
      />
    );
  }
  const { text, subject, usage } = state.value;
  return (
    <div className="space-y-2">
      <div className="max-h-[50dvh] overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 text-sm">
        {subject && <p className="mb-2 font-semibold">{subject}</p>}
        {text}
      </div>
      {usage && <LLMUsageBadge usage={usage} />}
    </div>
  );
}

function UseButtons({
  lng,
  single,
  onUse,
}: {
  lng: Language;
  single: boolean;
  onUse: (use: WritingUse) => void;
}) {
  const { t } = useTranslation(lng);
  if (single) {
    return <Button onClick={() => onUse('replace')}>{t('workbench.assist.writing.use')}</Button>;
  }
  return (
    <>
      <Button variant="outline" onClick={() => onUse('add')}>
        {t('workbench.assist.writing.add')}
      </Button>
      <Button onClick={() => onUse('replace')}>{t('workbench.assist.writing.replace')}</Button>
    </>
  );
}
