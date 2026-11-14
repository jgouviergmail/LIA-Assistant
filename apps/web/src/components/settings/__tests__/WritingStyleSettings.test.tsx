/**
 * WritingStyleSettings — what LIA learned of how the person writes (ADR-383).
 *
 * The real hook chain runs (account query, mutations); only the HTTP client is
 * replaced. Proven: the first load, the learned profile shown as TEXT, the switch
 * saved and its state answered, a failed save said, forgetting behind a
 * confirmation with the focus handed back to the switch, and a failed read retried.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeUser } from '@/__tests__/factories';
import { renderWithProviders, screen, userEvent, waitFor } from '@/__tests__/test-utils';
import type { WritingStyle } from '@/types/writing-style';

const { get, patch, del } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), del: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...original, default: { ...original.default, get, patch, delete: del } };
});
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: makeUser({ id: 'writer', timezone: 'Europe/Paris' }) }),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { WritingStyleSettings, writingStyleState } from '../WritingStyleSettings';

const PREFIX = 'settings.writing_style';

function style(over: Partial<WritingStyle> = {}): WritingStyle {
  return {
    enabled: true,
    profile: 'Writes « Salut », signs <b>Seb</b>.',
    mails_read: 12,
    learned_at: '2026-11-13T09:00:00Z',
    renews_at: '2026-12-13T09:00:00Z',
    ...over,
  };
}

function render() {
  return renderWithProviders(<WritingStyleSettings lng="en" />);
}

async function theSwitch() {
  return screen.findByRole('switch', { name: `${PREFIX}.enable` });
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(style());
});

describe('writingStyleState', () => {
  it('says what was learned, too little, nothing yet, or nothing while off', () => {
    expect(writingStyleState(style())).toBe('learned');
    expect(writingStyleState(style({ profile: null, mails_read: 2 }))).toBe('too_few');
    const none = { profile: null, mails_read: null, learned_at: null, renews_at: null };
    expect(writingStyleState(style(none))).toBe('nothing_yet');
    expect(writingStyleState(style({ ...none, enabled: false }))).toBe('off_nothing');
  });
});

describe('WritingStyleSettings', () => {
  it('shows the learned profile as text, with its switch on', async () => {
    render();

    expect(await theSwitch()).toHaveAttribute('aria-checked', 'true');
    expect(get).toHaveBeenCalledWith('/writing-style', expect.anything());
    // Model output is text, never markup.
    expect(screen.getByText('Writes « Salut », signs <b>Seb</b>.')).toBeInTheDocument();
    expect(screen.getByText(`${PREFIX}.learned_meta`)).toBeInTheDocument();
  });

  it('saves the switch and shows the state the server answers', async () => {
    patch.mockResolvedValue(style({ enabled: false }));
    render();
    const control = await theSwitch();

    await userEvent.click(control);

    await waitFor(() => expect(control).toHaveAttribute('aria-checked', 'false'));
    expect(patch).toHaveBeenCalledWith('/writing-style', { writing_style_enabled: false }, undefined);
    expect(screen.getByText(`${PREFIX}.off_kept`)).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith(`${PREFIX}.switched_off`);
    expect(control).toHaveFocus();
  });

  it('says a failed save and keeps what is shown', async () => {
    patch.mockRejectedValue(new Error('down'));
    render();
    const control = await theSwitch();

    await userEvent.click(control);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
    expect(control).toHaveAttribute('aria-checked', 'true');
  });

  it('forgets only after confirming, and hands the focus back to the switch', async () => {
    del.mockResolvedValue(undefined);
    render();
    const control = await theSwitch();

    await userEvent.click(screen.getByRole('button', { name: `${PREFIX}.forget` }));
    expect(del).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(
      Array.from(dialog.querySelectorAll('button')).find(
        button => button.textContent === `${PREFIX}.forget`
      )!
    );

    await waitFor(() => expect(del).toHaveBeenCalledWith('/writing-style', expect.anything()));
    await waitFor(() => expect(screen.getByText(`${PREFIX}.nothing_yet`)).toBeInTheDocument());
    expect(screen.queryByText('Writes « Salut », signs <b>Seb</b>.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `${PREFIX}.forget` })).not.toBeInTheDocument();
    await waitFor(() => expect(control).toHaveFocus());
    expect(toast.success).toHaveBeenCalledWith(`${PREFIX}.forgotten`);
  });

  it('says too few sent e-mails, with no forget button hidden behind it', async () => {
    get.mockResolvedValue(style({ profile: null, mails_read: 2 }));
    render();

    expect(await screen.findByText(`${PREFIX}.too_few`)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${PREFIX}.forget` })).toBeInTheDocument();
  });

  it('offers to retry a failed read, and retries it', async () => {
    get.mockRejectedValueOnce(new Error('down'));
    render();

    await userEvent.click(await screen.findByRole('button', { name: 'common.retry' }));

    expect(await theSwitch()).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
  });
});
