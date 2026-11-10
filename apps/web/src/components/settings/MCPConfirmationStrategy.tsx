'use client';

import { useState } from 'react';
import type { TFunction } from 'i18next';
import { Layers, ListChecks, ShieldCheck } from '@/lib/icons';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { useMCPBehaviorPreview } from '@/hooks/useMCPServerBehavior';
import {
  confirmationChoiceOf,
  confirmationValueOf,
  type MCPConfirmationChoice,
  type MCPQuestionLoss,
  type UserMCPDefaults,
} from '@/lib/mcp-behavior';
import { MCPChoiceCards, type MCPChoice } from './MCPChoiceCards';
import { MCPConfirmationLooseningDialog } from './MCPConfirmationLooseningDialog';

const PREFIX = 'settings.mcp.confirmation';

interface Props {
  /** The account whose strategy this is (the servers list's owner). */
  ownerId: string | undefined;
  defaults: UserMCPDefaults | undefined;
  /** Re-reads the server list, whose defaults the change moved. */
  onSaved: () => Promise<void> | void;
  t: TFunction;
}

/** « always ask » / « follow the declarations », as the default currently gives it. */
export function currentlyLabel(always: boolean, t: TFunction): string {
  return t(`${PREFIX}.current_${always ? 'always' : 'as_declared'}`);
}

/**
 * The account's confirmation strategy (spec 2026-10-30 D2, owner decision on alerts).
 *
 * What the person's servers inherit when they never chose. Never chosen, it follows
 * the instance default and says what that is. A change that would make LIA ask less
 * is shown first — the API lists what LIA would no longer ask about — and applies
 * only once the person confirms; nothing is locked.
 */
export function MCPConfirmationStrategy({ ownerId, defaults, onSaved, t }: Props) {
  const toast = useApplicationAccountToast(ownerId);
  const { previewStrategy } = useMCPBehaviorPreview();
  const { mutate: patchProfile } = useApiMutation<{ mcp_hitl_required: boolean | null }, unknown>({
    method: 'PATCH',
    componentName: 'MCPConfirmationStrategy',
    retainResponse: false,
  });
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{
    value: boolean | null;
    losses: MCPQuestionLoss[];
  } | null>(null);
  const current = confirmationChoiceOf(defaults?.confirmation_account);

  // The caller holds `busy` from the first click to the end: no second choice slips in.
  const apply = async (value: boolean | null) => {
    try {
      await patchProfile(`/users/${ownerId}`, { mcp_hitl_required: value });
      await onSaved();
      toast.success(t(`${PREFIX}.saved`));
    } catch {
      toast.error(t('common.error'));
    }
  };

  const choose = async (choice: MCPConfirmationChoice) => {
    if (!ownerId || busy || choice === current) return;
    const value = confirmationValueOf(choice);
    setBusy(true);
    try {
      const preview = await previewStrategy(value);
      if (preview && preview.questions_lost.length > 0)
        return setPending({ value, losses: preview.questions_lost });
      await apply(value);
    } catch {
      toast.error(t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (value: boolean | null) => {
    setPending(null);
    setBusy(true);
    try {
      await apply(value);
    } finally {
      setBusy(false);
    }
  };

  // Not read yet: nothing is shown rather than a choice that may not be the account's.
  if (!defaults) return null;

  const choices: MCPChoice<MCPConfirmationChoice>[] = [
    {
      value: 'always',
      label: t(`${PREFIX}.options.always.label`),
      description: t(`${PREFIX}.options.always.description`),
      icon: ShieldCheck,
    },
    {
      value: 'as_declared',
      label: t(`${PREFIX}.options.as_declared.label`),
      description: t(`${PREFIX}.options.as_declared.description`),
      icon: ListChecks,
    },
    {
      value: 'inherit',
      label: t(`${PREFIX}.options.inherit.label`),
      description: t(`${PREFIX}.options.inherit.description`, {
        value: currentlyLabel(defaults.confirmation_instance, t),
      }),
      icon: Layers,
    },
  ];

  return (
    <>
      <MCPChoiceCards
        legend={t(`${PREFIX}.strategy_legend`)}
        hint={t(`${PREFIX}.strategy_hint`)}
        value={current}
        choices={choices}
        onChange={choice => void choose(choice)}
        busy={busy}
      />
      <MCPConfirmationLooseningDialog
        losses={pending?.losses ?? null}
        onCancel={() => setPending(null)}
        onConfirm={() => void confirm(pending?.value ?? null)}
        t={t}
      />
    </>
  );
}
