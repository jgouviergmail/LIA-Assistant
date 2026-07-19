/**
 * HitlActionCard — approval card (Lot 1 P1-V1).
 *
 * Oracles are role/name and visible state (repo a11y contract): backend-driven
 * buttons with translated accessible names, per-kind content, disabled
 * submitting state, terminal resolved/expired states, and the wire action id
 * passed through verbatim on click.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { HitlActionCard } from '@/components/chat/HitlActionCard';
import type { HitlCardState, NormalizedHitlPayload } from '@/types/hitl';

// i18n: identity translator exposing the key — name assertions stay stable
// across locales (the real translations are covered by the parity hook).
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && typeof options.count === 'number' ? `${key}:${options.count}` : key,
  }),
}));

function payload(overrides: Partial<NormalizedHitlPayload> = {}): NormalizedHitlPayload {
  return {
    messageId: 'hitl_abc',
    kind: 'tool_confirmation',
    actions: [
      { action: 'confirm', label: 'confirm', style: 'primary' },
      { action: 'cancel', label: 'cancel', style: 'destructive' },
    ],
    toolName: 'send_email_tool',
    toolArgs: { to: 'a@b.c', subject: 'Hello' },
    ...overrides,
  };
}

function cardState(overrides: Partial<HitlCardState> = {}): HitlCardState {
  return {
    status: 'awaiting',
    payload: payload(),
    resolution: null,
    submittedAction: null,
    ...overrides,
  };
}

describe('HitlActionCard — rendering by kind', () => {
  it('renders nothing when no card is active', () => {
    const { container } = render(
      <HitlActionCard
        hitl={{ status: 'none', payload: null, resolution: null, submittedAction: null }}
        onAction={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('tool confirmation: title, tool name and both buttons by accessible name', () => {
    render(<HitlActionCard hitl={cardState()} onAction={vi.fn()} />);

    expect(screen.getByText('chat.hitl.title.tool_confirmation')).toBeInTheDocument();
    expect(screen.getByText('send_email_tool')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.hitl.actions.confirm' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'chat.hitl.actions.cancel' })).toBeEnabled();
  });

  it('draft: renders typed email fields', () => {
    render(
      <HitlActionCard
        hitl={cardState({
          payload: payload({
            kind: 'draft_critique',
            draftId: 'd1',
            draftType: 'email',
            draftContent: { to: 'x@y.z', subject: 'Sujet test', body: 'Corps.' },
          }),
        })}
        onAction={vi.fn()}
      />
    );

    expect(screen.getByText('chat.hitl.title.draft_critique')).toBeInTheDocument();
    expect(screen.getByText('x@y.z')).toBeInTheDocument();
    expect(screen.getByText('Sujet test')).toBeInTheDocument();
  });

  it('destructive: warning banner with affected count and verbatim wire action', async () => {
    const onAction = vi.fn();
    render(
      <HitlActionCard
        hitl={cardState({
          payload: payload({
            kind: 'destructive_confirm',
            severity: 'critical',
            operationType: 'delete_emails',
            affectedCount: 15,
            actions: [
              { action: 'confirm_delete', label: 'confirm_deletion', style: 'destructive' },
              { action: 'cancel', label: 'keep_items', style: 'secondary' },
            ],
          }),
        })}
        onAction={onAction}
      />
    );

    expect(screen.getByText('chat.hitl.affected_count:15')).toBeInTheDocument();
    const confirmBtn = screen.getByRole('button', { name: 'chat.hitl.actions.confirm_deletion' });
    await userEvent.click(confirmBtn);
    // Wire id passes through VERBATIM — the backend canonicalizes.
    expect(onAction).toHaveBeenCalledWith('confirm_delete', 'chat.hitl.actions.confirm_deletion');
  });

  it('for_each: iteration scale is displayed', () => {
    render(
      <HitlActionCard
        hitl={cardState({
          payload: payload({
            kind: 'for_each_confirmation',
            severity: 'warning',
            affectedCount: 8,
            previewItems: [{ name: 'Jean' }],
          }),
        })}
        onAction={vi.fn()}
      />
    );

    expect(screen.getByText('chat.hitl.affected_count:8')).toBeInTheDocument();
  });
});

describe('HitlActionCard — lifecycle states', () => {
  it('submitting disables every button', () => {
    render(
      <HitlActionCard
        hitl={cardState({ status: 'submitting', submittedAction: 'confirm' })}
        onAction={vi.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'chat.hitl.actions.confirm' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'chat.hitl.actions.cancel' })).toBeDisabled();
  });

  it('resolved shows the outcome badge instead of buttons', () => {
    render(
      <HitlActionCard
        hitl={cardState({
          status: 'resolved',
          resolution: 'confirmed',
          submittedAction: 'confirm',
        })}
        onAction={vi.fn()}
      />
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('chat.hitl.resolved.confirmed')).toBeInTheDocument();
  });

  it('resolved via_text shows its own badge', () => {
    render(
      <HitlActionCard
        hitl={cardState({ status: 'resolved', resolution: 'via_text' })}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText('chat.hitl.resolved.via_text')).toBeInTheDocument();
  });

  it('expired shows the expiry note without buttons', () => {
    render(<HitlActionCard hitl={cardState({ status: 'expired' })} onAction={vi.fn()} />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('chat.hitl.expired')).toBeInTheDocument();
  });

  it('clicking cancel forwards the wire id and its translated label', async () => {
    const onAction = vi.fn();
    render(<HitlActionCard hitl={cardState()} onAction={onAction} />);

    await userEvent.click(screen.getByRole('button', { name: 'chat.hitl.actions.cancel' }));
    expect(onAction).toHaveBeenCalledWith('cancel', 'chat.hitl.actions.cancel');
  });
});

describe('HitlActionCard — draft inline edit (P1-V2)', () => {
  function draftWithEdit(): HitlCardState {
    return cardState({
      payload: payload({
        kind: 'draft_critique',
        draftId: 'd1',
        draftContent: { to: 'a@b.c', subject: 'Hello', body: 'Hi' },
        actions: [
          { action: 'confirm', label: 'confirm', style: 'primary' },
          { action: 'edit', label: 'edit', style: 'secondary' },
          { action: 'cancel', label: 'cancel', style: 'destructive' },
        ],
      }),
    });
  }

  it('edit button toggles the instructions form instead of submitting', async () => {
    const onAction = vi.fn();
    render(<HitlActionCard hitl={draftWithEdit()} onAction={onAction} />);

    await userEvent.click(screen.getByRole('button', { name: 'chat.hitl.actions.edit' }));

    expect(onAction).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox', { name: 'chat.hitl.edit.placeholder' })).toHaveFocus();
    // Action buttons are hidden while editing.
    expect(
      screen.queryByRole('button', { name: 'chat.hitl.actions.confirm' })
    ).not.toBeInTheDocument();
  });

  it('submit is disabled on blank instructions, then forwards them as message', async () => {
    const onAction = vi.fn();
    render(<HitlActionCard hitl={draftWithEdit()} onAction={onAction} />);

    await userEvent.click(screen.getByRole('button', { name: 'chat.hitl.actions.edit' }));
    const submit = screen.getByRole('button', { name: 'chat.hitl.edit.submit' });
    expect(submit).toBeDisabled();

    await userEvent.type(
      screen.getByRole('textbox', { name: 'chat.hitl.edit.placeholder' }),
      'Raccourcis le message'
    );
    await userEvent.click(submit);

    expect(onAction).toHaveBeenCalledWith('edit', 'Raccourcis le message', 'Raccourcis le message');
  });

  it('escape leaves edit mode and restores the buttons', async () => {
    render(<HitlActionCard hitl={draftWithEdit()} onAction={vi.fn()} />);

    await userEvent.click(screen.getByRole('button', { name: 'chat.hitl.actions.edit' }));
    await userEvent.keyboard('{Escape}');

    expect(screen.getByRole('button', { name: 'chat.hitl.actions.confirm' })).toBeVisible();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('a re-presented draft (new messageId) leaves edit mode automatically', async () => {
    const first = draftWithEdit();
    const { rerender } = render(<HitlActionCard hitl={first} onAction={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: 'chat.hitl.actions.edit' }));
    expect(screen.getByRole('textbox')).toBeInTheDocument();

    const next = draftWithEdit();
    next.payload = { ...next.payload!, messageId: 'hitl_new' };
    rerender(<HitlActionCard hitl={next} onAction={vi.fn()} />);

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'chat.hitl.actions.edit' })).toBeVisible();
  });

  it('non-draft cards never show an edit toggle even if the wire offers it', () => {
    const state = cardState({
      payload: payload({
        actions: [
          { action: 'confirm', label: 'confirm', style: 'primary' },
          { action: 'edit', label: 'edit', style: 'secondary' },
        ],
      }),
    });
    const onAction = vi.fn();
    render(<HitlActionCard hitl={state} onAction={onAction} />);

    // The edit button submits directly (no toggle) on non-draft kinds — the
    // normalizer filters it out upstream anyway; this is defense in depth.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
