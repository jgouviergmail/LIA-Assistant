'use client';

import { useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useTranslation } from 'react-i18next';
import { HitlActionCard } from '@/components/chat/HitlActionCard';
import type { HitlCardState } from '@/types/hitl';
import { HOME_PRODUCT_DEMO_KEY } from './scenes';

const MarkdownContent = dynamic(() =>
  import('@/components/chat/MarkdownContent').then(module => module.MarkdownContent)
);

/** The real approval component, with a strictly local fictional lifecycle. */
export function ProductApproval() {
  const { t } = useTranslation();
  const [decision, setDecision] = useState<'confirm' | 'cancel' | null>(null);
  const [editInstructions, setEditInstructions] = useState('');
  const resetRef = useRef<HTMLButtonElement>(null);
  const key = `${HOME_PRODUCT_DEMO_KEY}.scenes.call`;
  const hitl: HitlCardState = {
    status: decision ? 'resolved' : 'awaiting',
    resolution: decision === 'confirm' ? 'confirmed' : decision === 'cancel' ? 'cancelled' : null,
    submittedAction: decision,
    payload: {
      messageId: 'landing-fictional-call',
      kind: 'draft_critique',
      draftId: 'landing-fictional-phone-draft',
      draftType: 'phone_call',
      draftContent: {
        callee_name: 'Les Jardins (Demo)',
        callee_phone: '+1 202 555 0100',
        objective: t(`${key}.result_3`),
      },
      actions: [
        { action: 'confirm', label: 'confirm', style: 'primary' },
        { action: 'edit', label: 'edit', style: 'secondary' },
        { action: 'cancel', label: 'cancel', style: 'destructive' },
      ],
    },
  };

  return (
    <div className="space-y-3">
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t(`${HOME_PRODUCT_DEMO_KEY}.approval_hint`)}
      </p>
      {/* Generated with render_confirmation_card(PHONE_CALL, surface=CHAT),
          then displayed with the chat's actual sanitizing renderer. */}
      <MarkdownContent content={t(`${key}.preview_html`)} />
      <HitlActionCard
        hitl={hitl}
        onAction={(action, _label, instructions) => {
          if (action === 'edit') {
            setEditInstructions(instructions ?? '');
            resetRef.current?.focus({ preventScroll: true });
            return;
          }
          if (action !== 'confirm' && action !== 'cancel') return;
          setDecision(action);
          // The acted-on button disappears in the real resolved card. Keep
          // the visitor on the stable reset control, never on the document.
          resetRef.current?.focus({ preventScroll: true });
        }}
      />
      <p role="status" className="text-xs leading-relaxed">
        {decision
          ? t(
              `${HOME_PRODUCT_DEMO_KEY}.approval_${decision === 'confirm' ? 'confirmed' : 'cancelled'}`
            )
          : editInstructions && t(`${HOME_PRODUCT_DEMO_KEY}.approval_edited`)}
      </p>
      {editInstructions && !decision && (
        <p className="text-xs leading-relaxed text-muted-foreground">{editInstructions}</p>
      )}
      <button
        ref={resetRef}
        type="button"
        onClick={() => {
          setDecision(null);
          setEditInstructions('');
        }}
        className="rounded-md px-2 py-2 text-xs font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {t(`${HOME_PRODUCT_DEMO_KEY}.approval_reset`)}
      </button>
    </div>
  );
}
