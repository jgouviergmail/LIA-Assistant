/**
 * AdminChainVerification — a sweep nobody runs by accident (ADR-263, lot 5).
 *
 * The oracles are the ones an operator's trust rests on: nothing runs on
 * opening, the scope actually travels to the API, a broken chain is named
 * rather than counted, and a failed sweep clears the previous result instead
 * of leaving a green list behind it.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AdminChainVerification } from '@/components/settings/AdminChainVerification';
import type { UserSuggestion } from '@/components/settings/AdminUserAutocomplete';

const dictionary: Record<string, string> = {
  'settings.admin.registers.verify_title': 'Verify integrity',
  'settings.admin.registers.verify_hint_all': 'Every sealed account',
  'settings.admin.registers.verify_hint_selected': '{{count}} accounts selected',
  'settings.admin.registers.verify_action': 'Verify',
  'settings.admin.registers.verify_running': 'Verifying',
  'settings.admin.registers.verify_failed': 'The verification did not complete',
  'settings.admin.registers.verify_all_ok': '{{count}} chains verified, all intact',
  'settings.admin.registers.verify_broken': '{{count}} broken chains',
  'settings.admin.registers.verify_partial': '{{checked}} of {{total}} accounts verified',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const template = dictionary[key] ?? key;
      return Object.entries(options ?? {}).reduce(
        (text, [name, value]) => text.replace(`{{${name}}}`, String(value)),
        template
      );
    },
    i18n: { language: 'en' },
  }),
}));

const get = vi.fn();
vi.mock('@/lib/api-client', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}));

vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

const ALICE: UserSuggestion = { id: 'user-a', email: 'alice@test.local' } as UserSuggestion;
const BOB: UserSuggestion = { id: 'user-b', email: 'bob@test.local' } as UserSuggestion;

const sweepOf = (rows: unknown[], total?: number) => ({
  rows,
  accounts_checked: rows.length,
  accounts_with_chain: total ?? rows.length,
  limit: 50,
});

const OK_ROW = {
  user_id: 'user-a',
  ok: true,
  entries: 10,
  pending: 0,
  payloads_checked: 9,
  broken_at_seq: null,
  reason: null,
};
const BROKEN_ROW = {
  user_id: 'user-b',
  ok: false,
  entries: 4,
  pending: 0,
  payloads_checked: 2,
  broken_at_seq: 3,
  reason: 'payload',
};

beforeEach(() => {
  get.mockReset();
});

describe('AdminChainVerification', () => {
  it('runs nothing on opening', () => {
    render(<AdminChainVerification users={[]} />);

    expect(get).not.toHaveBeenCalled();
    expect(screen.queryByText(/intact/i)).not.toBeInTheDocument();
  });

  it('sweeps every account when none is selected', async () => {
    get.mockResolvedValue(sweepOf([OK_ROW]));

    render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(get.mock.calls[0][0]).toBe('/admin/effects/chain/verify?deep=true');
    expect(screen.getByText('Every sealed account')).toBeInTheDocument();
  });

  it('carries EVERY selected account into the request', async () => {
    get.mockResolvedValue(sweepOf([OK_ROW, OK_ROW]));

    render(<AdminChainVerification users={[ALICE, BOB]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(get.mock.calls[0][0]).toContain('user_ids=user-a');
    expect(get.mock.calls[0][0]).toContain('user_ids=user-b');
    expect(screen.getByText('2 accounts selected')).toBeInTheDocument();
  });

  it('names the accounts whose chain broke, with the reason and the position', async () => {
    get.mockResolvedValue(sweepOf([BROKEN_ROW, OK_ROW]));

    render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    expect(await screen.findByText('1 broken chains')).toBeInTheDocument();
    expect(screen.getByText(/user-b — payload @ 3/)).toBeInTheDocument();
    expect(screen.queryByText(/all intact/)).not.toBeInTheDocument();
  });

  it('reports a clean sweep only when nothing broke', async () => {
    get.mockResolvedValue(sweepOf([OK_ROW, { ...OK_ROW, user_id: 'user-c' }]));

    render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    expect(await screen.findByText('2 chains verified, all intact')).toBeInTheDocument();
  });

  it('CLEARS a previous result when a later sweep fails', async () => {
    get.mockResolvedValueOnce(sweepOf([OK_ROW]));

    render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));
    expect(await screen.findByText('1 chains verified, all intact')).toBeInTheDocument();

    get.mockRejectedValueOnce(new Error('boom'));
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    expect(await screen.findByText('The verification did not complete')).toBeInTheDocument();
    expect(screen.queryByText(/all intact/)).not.toBeInTheDocument();
  });

  it('STATES how many accounts it did not reach', async () => {
    // Fifty green rows must never read as an answer about five hundred
    // accounts: the cap is stated, never applied in silence (ADR-185).
    get.mockResolvedValue(sweepOf([OK_ROW], 12));

    render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    expect(await screen.findByText('1 of 12 accounts verified')).toBeInTheDocument();
  });

  it('says nothing about a cap when the sweep reached everything', async () => {
    get.mockResolvedValue(sweepOf([OK_ROW]));

    render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));
    await screen.findByText('1 chains verified, all intact');

    expect(screen.queryByText(/accounts verified/)).not.toBeInTheDocument();
  });

  it('announces its outcome in a live region', async () => {
    get.mockResolvedValue(sweepOf([OK_ROW]));

    const { container } = render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));
    await screen.findByText('1 chains verified, all intact');

    expect(container.querySelector('[aria-live="polite"]')?.textContent).toContain('intact');
  });
});

describe('AdminChainVerification — the alert is composed the way the design system expects', () => {
  it('never puts the broken-chain LIST inside a paragraph', async () => {
    // `AlertDescription` renders a <p>, and a <ul> inside one is invalid HTML:
    // the browser closes the paragraph early and the layout silently breaks.
    // A snapshot would not catch it; the parent chain does.
    get.mockResolvedValue(sweepOf([BROKEN_ROW]));

    const { container } = render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));
    await screen.findByText('1 broken chains');

    const list = container.querySelector('ul');
    expect(list).not.toBeNull();
    expect(list?.closest('p')).toBeNull();
  });

  it('carries the variant icon the charter gives every alert', async () => {
    get.mockResolvedValue(sweepOf([OK_ROW]));

    const { container } = render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));
    await screen.findByText('1 chains verified, all intact');

    const alert = container.querySelector('[role="alert"]');
    expect(alert?.querySelector('svg')).not.toBeNull();
  });

  it('does not nest one live region inside another', async () => {
    // `Alert` is already `aria-live`; a hand-rolled wrapper around it makes a
    // screen reader announce the outcome twice.
    get.mockResolvedValue(sweepOf([OK_ROW]));

    const { container } = render(<AdminChainVerification users={[]} />);
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));
    await screen.findByText('1 chains verified, all intact');

    const regions = container.querySelectorAll('[aria-live]');
    expect(regions).toHaveLength(1);
    expect(regions[0].getAttribute('role')).toBe('alert');
  });
});
