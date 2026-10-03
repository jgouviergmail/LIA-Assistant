'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useConfirm } from '@/components/ui/use-confirm';
import type { CardCompositionDraft } from '@/types/card-actions';

interface Options {
  initialMessage?: string;
  initialComposition?: CardCompositionDraft;
  saveDraft: (text: string, composition?: CardCompositionDraft) => void;
  disabled: boolean;
}

export function useCardComposition({
  initialMessage = '',
  initialComposition,
  saveDraft,
  disabled,
}: Options) {
  const { t } = useTranslation();
  const { confirm, confirmDialog } = useConfirm();
  const [composition, setComposition] = useState<CardCompositionDraft | null>(() =>
    initialComposition?.text === initialMessage ? initialComposition : null
  );
  const [prefill, setPrefill] = useState({ text: '', nonce: 0 });
  const current = useRef(initialMessage);
  const selected = useRef(composition);
  const pending = useRef(false);
  const blocked = useRef(disabled);
  useEffect(() => {
    blocked.current = disabled;
  }, [disabled]);

  const changeSelection = useCallback((value: CardCompositionDraft | null) => {
    selected.current = value;
    setComposition(value);
  }, []);
  const onTextChange = useCallback(
    (text: string) => {
      current.current = text;
      const next = text.trim() && selected.current ? { ...selected.current, text } : null;
      changeSelection(next);
      saveDraft(text, next ?? undefined);
    },
    [changeSelection, saveDraft]
  );
  const prefillText = useCallback(
    (text: string) => {
      changeSelection(null);
      current.current = text;
      setPrefill(value => ({ text, nonce: value.nonce + 1 }));
      saveDraft(text);
    },
    [changeSelection, saveDraft]
  );
  const removeComposition = useCallback(() => {
    changeSelection(null);
    saveDraft(current.current);
  }, [changeSelection, saveDraft]);
  const onCompose = useCallback(
    async (draft: CardCompositionDraft) => {
      if (pending.current || blocked.current) return;
      pending.current = true;
      const before = current.current;
      try {
        if (before.trim() && before !== draft.text) {
          const confirmed = await confirm({
            title: t('chat.card_actions.replace_title'),
            description: t('chat.card_actions.replace_description'),
            confirmLabel: t('chat.card_actions.replace_confirm'),
            destructive: false,
          });
          if (!confirmed || current.current !== before || blocked.current) return;
        }
        changeSelection(draft);
        current.current = draft.text;
        setPrefill(value => ({ text: draft.text, nonce: value.nonce + 1 }));
        saveDraft(draft.text, draft);
      } finally {
        pending.current = false;
      }
    },
    [changeSelection, confirm, saveDraft, t]
  );
  return {
    composition,
    prefill,
    onCompose,
    onAvailableCompose: disabled ? undefined : onCompose,
    onTextChange,
    prefillText,
    removeComposition,
    confirmDialog,
  };
}

export function cardCompositionDisabled(
  locks: { input: boolean; apiUsable: boolean },
  hitlBlocked: boolean
): boolean {
  return locks.input || !locks.apiUsable || hitlBlocked;
}
