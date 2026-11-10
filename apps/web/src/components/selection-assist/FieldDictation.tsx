'use client';
/** A dedicated caret control: no capture before the click and no write to a retired field. */
import { useLayoutEffect, useRef, useState } from 'react';
import { Mic, X } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { useSelectionTargetValidity } from '@/hooks/useSelectionTargetValidity';
import {
  applySelection,
  dismissSelection,
  targetIsCurrent,
  type ApplyResult,
  type SelectionTarget,
} from '@/lib/selection-assist/targets';
import type { SelectionContextValue } from './context';
import { DictationAct } from './DictationAct';
import { SelectionLayer } from './SelectionLayer';
import { SelectionAnswerView } from './SelectionAnswerView';

export function FieldDictation({
  context,
  target,
}: {
  context: SelectionContextValue;
  target: SelectionTarget;
}) {
  const { lng, store } = context;
  const { t } = useTranslation(lng);
  const [recording, setRecording] = useState(false);
  const [answer, setAnswer] = useState<{ text: string; result: ApplyResult } | null>(null);
  // The recorder calls onWords and onEnd in the same tick, before React renders the answer.
  const keepAnswer = useRef(false);
  const alive = useRef(true);
  const control = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useLayoutEffect(() => {
    if (recording) control.current?.querySelector('button')?.focus({ preventScroll: true });
  }, [recording]);
  const current = () => alive.current && store.getSnapshot() === target;
  const retire = () => {
    if (current()) store.dismiss('focus');
  };
  const close = () => {
    if (!current()) return;
    store.dismiss();
    dismissSelection(target);
  };
  useSelectionTargetValidity(
    target,
    () => {
      if (!current()) return;
      // Typing moves an idle caret; only an in-flight recording or answer is retired.
      if (recording || answer) retire();
      else store.set(null);
    },
    retire
  );
  const insert = (words: string) => {
    if (!current()) return;
    const result = applySelection(target, words);
    if (result === 'applied') return;
    keepAnswer.current = true;
    setRecording(false);
    setAnswer({ text: words, result });
  };
  return (
    <SelectionLayer
      target={target}
      toolbar={!answer}
      title={t('selectionAssist.voice.dictate')}
      onClose={close}
      restoreFocus={store.shouldRestoreFocus}
    >
      {answer ? (
        <>
          <SelectionAnswerView
            text={answer.text}
            usage={null}
            target={target}
            lng={lng}
            stale={answer.result === 'stale'}
            onApplied={close}
          />
          {answer.result !== 'too_long' && (
            <p role="status">{t(`selectionAssist.${answer.result}`)}</p>
          )}
        </>
      ) : (
        <span ref={control}>
          {recording ? (
            <DictationAct
              lng={lng}
              onWords={insert}
              onEnd={() => {
                if (!keepAnswer.current) close();
              }}
            />
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-9 gap-1.5 px-2 text-xs"
              onClick={() => {
                if (current() && targetIsCurrent(target)) setRecording(true);
              }}
            >
              <Mic className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              {t('selectionAssist.voice.dictate')}
            </Button>
          )}
        </span>
      )}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-9 w-9"
        aria-label={t('common.close')}
        data-selection-close=""
        onClick={close}
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </Button>
    </SelectionLayer>
  );
}
