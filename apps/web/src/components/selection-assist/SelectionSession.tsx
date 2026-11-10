'use client';
/** One frozen target, one model call, one explicit application. */
import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useAssistCall } from '@/hooks/useAssistCall';
import { useSelectionTargetValidity } from '@/hooks/useSelectionTargetValidity';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { requestSelection } from '@/lib/selection-assist/transport';
import type {
  SelectionAction,
  SelectionAnswer,
  SelectionOffer,
  ModelSelectionAction,
} from '@/lib/selection-assist/contracts';
import {
  targetIsCurrent,
  dismissSelection,
  type SelectionTarget,
} from '@/lib/selection-assist/targets';
import type { SelectionContextValue } from './context';
import { SelectionLayer } from './SelectionLayer';
import { SelectionToolbar } from './SelectionToolbar';
import { SelectionBubble, SelectionQuestion, SelectionProgress } from './SelectionBubble';
import { SelectionAnswerView } from './SelectionAnswerView';
import { SelectionTranslation } from './SelectionTranslation';
import { SelectionResearch } from './SelectionResearch';
import { requestReadAloud, type SelectionSpeech } from '@/lib/selection-assist/speech';
import { HeardWords, VoiceCost } from '@/components/workbench/assist/AssistPanel';
import { useAskLia } from '@/components/workbench/assist/useAskLia';

interface SelectionInstructions {
  question?: string;
  target_language?: string;
}

export function SelectionSession({
  context,
  offer,
  target,
}: {
  context: SelectionContextValue;
  offer: SelectionOffer;
  target: SelectionTarget;
}) {
  const { lng, store, onProposal } = context;
  const { t } = useTranslation(lng);
  const [action, setAction] = useState<SelectionAction | null>(null);
  const [instructions, setInstructions] = useState<SelectionInstructions>({});
  const [stale, setStale] = useState(false);
  const chosenOnce = useRef(false);
  const requesting = useRef(false);
  const speaking = useRef(false);
  const transport = useCallback(
    (path: string, body: object, signal: AbortSignal) =>
      requestSelection(path, body, signal, offer),
    [offer]
  );
  const call = useAssistCall<SelectionAnswer>(target.id, transport);
  const speech = useAssistCall<SelectionSpeech>(target.id, requestReadAloud);
  const askLia = useAskLia(lng);
  const { stop } = call;
  const close = () => {
    stop();
    speech.stop();
    store.dismiss();
    dismissSelection(target);
  };
  useSelectionTargetValidity(
    target,
    () => {
      setStale(true);
      if (call.state.status === 'running') stop();
      if (speech.state.status === 'running') speech.stop();
    },
    () => store.set(null)
  );

  const ask = async (chosen: ModelSelectionAction, inputs: SelectionInstructions = {}) => {
    if (requesting.current) return;
    if (!targetIsCurrent(target)) {
      setStale(true);
      return;
    }
    requesting.current = true;
    const answer = await call.run('/tool-assists/text/selection/stream', {
      mode: target.mode,
      action: chosen,
      text: target.text,
      origin: 'page',
      ...inputs,
    });
    requesting.current = false;
    if (!answer || answer.proposal.kind === 'text' || answer.proposal.kind === 'research') return;
    if (!targetIsCurrent(target)) {
      setStale(true);
      return;
    }
    if (answer.usage) toast(<LLMUsageBadge usage={answer.usage} />);
    onProposal?.(answer.proposal);
    store.set(null);
  };
  const read = async () => {
    if (speaking.current || !targetIsCurrent(target)) return;
    speaking.current = true;
    await speech.run('/tool-assists/read-aloud', { text: target.text });
    speaking.current = false;
  };
  const choose = (chosen: SelectionAction) => {
    if (chosenOnce.current) return;
    if (!targetIsCurrent(target)) {
      setStale(true);
      return;
    }
    chosenOnce.current = true;
    if (chosen === 'lia') {
      store.dismiss('focus');
      dismissSelection(target);
      askLia(target.text);
      return;
    }
    setAction(chosen);
    if (chosen === 'read') void read();
    else if (chosen !== 'ask' && chosen !== 'translate') void ask(chosen);
  };
  const proposal = call.state.status === 'done' ? call.state.value.proposal : null;
  const usage = call.state.status === 'done' ? call.state.value.usage : null;
  const answerText = proposal?.kind === 'text' ? proposal.text : null;
  return (
    <SelectionLayer
      target={target}
      toolbar={!action}
      title={t(action ? `selectionAssist.actions.${action}` : 'selectionAssist.label')}
      onClose={close}
      restoreFocus={store.shouldRestoreFocus}
    >
      {!action ? (
        <SelectionToolbar
          target={target}
          lng={lng}
          offer={offer}
          creates={!!onProposal}
          onAction={choose}
          onClose={close}
        />
      ) : (
        <SelectionBubble lng={lng} action={action} onClose={close}>
          {stale && (
            <p role="status" className="mb-2 text-sm">
              {t('selectionAssist.stale')}
            </p>
          )}
          {call.state.status === 'idle' && !stale && (
            <SelectionInstructionForm
              action={action}
              lng={lng}
              offer={offer}
              onSubmit={(chosen, inputs) => {
                setInstructions(inputs);
                void ask(chosen, inputs);
              }}
            />
          )}
          <SelectionProgress
            lng={lng}
            action={action}
            state={call.state}
            onRetry={() => {
              if (action !== 'read' && action !== 'lia') void ask(action, instructions);
            }}
          />
          <SelectionProgress
            lng={lng}
            action="read"
            state={speech.state}
            onRetry={() => void read()}
          />
          {speech.state.status === 'done' && (
            <>
              <HeardWords
                lng={lng}
                label={t('selectionAssist.actions.read')}
                answer={speech.state.value}
              />
              <VoiceCost lng={lng} cost={speech.state.value.cost_eur} />
            </>
          )}
          {answerText !== null && (
            <SelectionAnswerView
              text={answerText}
              target={target}
              lng={lng}
              stale={stale}
              usage={usage}
              onApplied={close}
            />
          )}
          {proposal?.kind === 'research' && (
            <SelectionResearch
              proposal={proposal}
              target={target}
              lng={lng}
              stale={stale}
              usage={usage}
              onApplied={close}
            />
          )}
        </SelectionBubble>
      )}
    </SelectionLayer>
  );
}

/** Actions needing an instruction share one admission stage before their paid request. */
function SelectionInstructionForm({
  action,
  lng,
  offer,
  onSubmit,
}: {
  action: SelectionAction;
  lng: Language;
  offer: SelectionOffer;
  onSubmit: (action: 'ask' | 'translate', instructions: SelectionInstructions) => void;
}) {
  if (action === 'ask')
    return (
      <SelectionQuestion
        lng={lng}
        limit={offer.question_max_chars}
        onAsk={question => onSubmit('ask', { question })}
      />
    );
  if (action === 'translate')
    return (
      <SelectionTranslation
        lng={lng}
        limit={offer.language_max_chars}
        onTranslate={language => onSubmit('translate', { target_language: language })}
      />
    );
  return null;
}
