'use client';
/** Review a proposal, copy it, or explicitly apply it to its still-current native target. */
import { useState, type ReactNode } from 'react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { LLMUsage } from '@/types/llm-usage';
import { Button } from '@/components/ui/button';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { copyText } from '@/lib/workbench/copy';
import {
  applySelection,
  targetIsCurrent,
  replacementFits,
  type SelectionTarget,
  type ApplyResult,
} from '@/lib/selection-assist/targets';

export function SelectionAnswerView({
  text,
  usage,
  target,
  lng,
  stale,
  onApplied,
  children,
}: {
  text: string;
  usage: LLMUsage | null;
  target: SelectionTarget;
  lng: Language;
  stale: boolean;
  onApplied: () => void;
  children?: ReactNode;
}) {
  const { t } = useTranslation(lng);
  const [notice, setNotice] = useState<ApplyResult | 'copied' | 'copy_failed' | null>(null);
  const applicable = !stale && targetIsCurrent(target) && replacementFits(target, text);
  const copy = async () => {
    try {
      await copyText(text);
      setNotice('copied');
    } catch {
      setNotice('copy_failed');
    }
  };
  const apply = () => {
    if (!applicable) return;
    const result = applySelection(target, text);
    if (result === 'applied') onApplied();
    else setNotice(result);
  };
  return (
    <div className="space-y-3">
      {children ?? (
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{text}</p>
      )}
      {usage && <LLMUsageBadge usage={usage} />}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => void copy()}>
          {t('selectionAssist.copy')}
        </Button>
        {target.mode === 'edit' && (
          <Button type="button" aria-disabled={!applicable} onClick={apply}>
            {t('selectionAssist.apply')}
          </Button>
        )}
      </div>
      {!stale && !replacementFits(target, text) && (
        <p role="status">{t('selectionAssist.too_long_result')}</p>
      )}
      {notice && (
        <p role="status" className="mt-2 text-sm">
          {t(`selectionAssist.${notice === 'too_long' ? 'too_long_result' : notice}`)}
        </p>
      )}
    </div>
  );
}
