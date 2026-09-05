/**
 * ChainSealCard — a claim only after a check (ADR-263, lot 5).
 *
 * Every oracle here is about what the card is allowed to SAY, and when. A
 * transparency surface that reassures before it verifies, or that leaves a
 * green verdict on screen after a failed check, is worse than no surface: it
 * spends the trust the registers were built to earn.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ChainSealCard } from '@/components/effects/ChainSealCard';
import type { ChainSeal, ChainVerdict } from '@/hooks/useChainSeal';

const dictionary: Record<string, string> = {
  'registers.seal.loading': 'Loading the sealing status',
  'registers.seal.disabled': 'Sealing is not enabled on this instance',
  'registers.seal.not_yet': 'Nothing sealed yet',
  'registers.seal.sealed_until': 'Journals sealed up to {{date}}',
  'registers.seal.pending': '{{count}} rows not sealed yet',
  'registers.seal.verify': 'Verify integrity',
  'registers.seal.verifying': 'Verifying',
  'registers.seal.verify_failed': 'The verification did not complete',
  'registers.seal.verdict_ok': 'Intact: {{count}} recomputed rows match',
  'registers.seal.verdict_broken': 'Break detected at position {{seq}}',
  'registers.seal.fingerprint': 'Final fingerprint:',
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

const state = {
  seal: undefined as ChainSeal | undefined,
  verdict: undefined as ChainVerdict | undefined,
  loading: false,
  verifying: false,
  error: null as Error | null,
  verify: vi.fn(),
};

vi.mock('@/hooks/useChainSeal', () => ({
  useChainSeal: () => state,
}));

const SEAL: ChainSeal = {
  sealing_enabled: true,
  entries: 42,
  sealed_until: '2026-09-04T18:00:00Z',
  pending: 3,
};

const VERDICT: ChainVerdict = {
  ok: true,
  entries: 42,
  sealed_until: '2026-09-04T18:00:00Z',
  pending: 3,
  payloads_checked: 41,
  payloads_skipped: 0,
  head_hash: 'a'.repeat(64),
  broken_at_seq: null,
  reason: null,
};

beforeEach(() => {
  state.seal = { ...SEAL };
  state.verdict = undefined;
  state.loading = false;
  state.verifying = false;
  state.error = null;
  state.verify = vi.fn();
});

describe('ChainSealCard', () => {
  it('states what is sealed without claiming anything is intact', () => {
    render(<ChainSealCard />);

    expect(screen.getByText(/Journals sealed up to/)).toBeInTheDocument();
    expect(screen.queryByText(/Intact/)).not.toBeInTheDocument();
  });

  it('names what is NOT sealed yet, rather than letting silence imply coverage', () => {
    render(<ChainSealCard />);

    expect(screen.getByText('3 rows not sealed yet')).toBeInTheDocument();
  });

  it('hides the pending line when everything is sealed', () => {
    state.seal = { ...SEAL, pending: 0 };

    render(<ChainSealCard />);

    expect(screen.queryByText(/rows not sealed yet/)).not.toBeInTheDocument();
  });

  it('says an instance that does not seal is not sealing, not that nothing happened', () => {
    state.seal = { ...SEAL, sealing_enabled: false, entries: 0, sealed_until: null };

    render(<ChainSealCard />);

    expect(screen.getByText(/Sealing is not enabled/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Verify/ })).not.toBeInTheDocument();
  });

  it('distinguishes « enabled but nothing sealed yet » from « disabled »', () => {
    state.seal = { ...SEAL, entries: 0, sealed_until: null, pending: 2 };

    render(<ChainSealCard />);

    expect(screen.getByText('Nothing sealed yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Verify/ })).toBeInTheDocument();
  });

  it('runs the verification only when asked', async () => {
    render(<ChainSealCard />);

    expect(state.verify).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /Verify/ }));

    await waitFor(() => expect(state.verify).toHaveBeenCalledTimes(1));
  });

  it('announces the verdict and the fingerprint a reader can note down', () => {
    state.verdict = { ...VERDICT };

    render(<ChainSealCard />);

    expect(screen.getByText('Intact: 41 recomputed rows match')).toBeInTheDocument();
    expect(screen.getByText(new RegExp('a'.repeat(64)))).toBeInTheDocument();
  });

  it('shows a break with the position that failed', () => {
    state.verdict = { ...VERDICT, ok: false, broken_at_seq: 17, reason: 'payload' };

    render(<ChainSealCard />);

    expect(screen.getByText('Break detected at position 17')).toBeInTheDocument();
    expect(screen.queryByText(/Intact/)).not.toBeInTheDocument();
  });

  it('shows NO verdict when the check itself failed', () => {
    state.error = new Error('boom');

    render(<ChainSealCard />);

    expect(screen.getByText('The verification did not complete')).toBeInTheDocument();
    expect(screen.queryByText(/Intact/)).not.toBeInTheDocument();
  });

  it('announces the outcome in a live region', () => {
    state.verdict = { ...VERDICT };

    const { container } = render(<ChainSealCard />);

    const live = container.querySelector('[aria-live="polite"]');
    expect(live).not.toBeNull();
    expect(live?.textContent).toContain('Intact');
  });

  it('holds the card geometry while the status loads', () => {
    state.loading = true;
    state.seal = undefined;

    render(<ChainSealCard />);

    // The skeleton speaks through its accessible name, not its text: it is a
    // placeholder, and a sighted reader must see geometry rather than words.
    expect(screen.getByRole('status', { name: 'Loading the sealing status' })).toBeInTheDocument();
  });
});
