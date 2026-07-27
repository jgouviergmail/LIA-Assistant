/**
 * AdminPersonalitiesSection — the personality catalogue: loading, listing in
 * `sort_order`, the load failure, and the four row actions. Two invariants
 * carry real consequences and are pinned here: the **default personality can
 * never be deleted** (refused before any confirmation is even asked), and
 * promoting an already-default personality is a no-op. Delete and translate
 * surface the server's own message when it provides one.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { answerConfirmDialog, renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import type { PersonalityResponse } from '@/types/personality';

const {
  fetchPersonalitiesAdmin,
  createPersonality,
  updatePersonality,
  deletePersonality,
  translatePersonality,
} = vi.hoisted(() => ({
  fetchPersonalitiesAdmin: vi.fn(),
  createPersonality: vi.fn(),
  updatePersonality: vi.fn(),
  deletePersonality: vi.fn(),
  translatePersonality: vi.fn(),
}));
vi.mock('@/lib/api/personality', () => ({
  fetchPersonalitiesAdmin,
  createPersonality,
  updatePersonality,
  deletePersonality,
  translatePersonality,
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import AdminPersonalitiesSection from '../AdminPersonalitiesSection';

const I18N = 'settings.admin.personalities';
const TIP = `${I18N}.tooltips`;

function personality(over: Partial<PersonalityResponse> = {}): PersonalityResponse {
  return {
    id: 'p1',
    code: 'coach',
    emoji: '🏅',
    is_default: false,
    is_active: true,
    sort_order: 0,
    prompt_instruction: 'Be encouraging.',
    translations: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  };
}

function render() {
  return renderWithProviders(<AdminPersonalitiesSection lng="en" collapsible={false} />);
}

async function renderLoaded(list: PersonalityResponse[] = [personality()]) {
  fetchPersonalitiesAdmin.mockResolvedValue(list);
  const utils = render();
  // The code is echoed in more than one place (responsive layouts) — match all.
  await screen.findAllByText('coach');
  return utils;
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchPersonalitiesAdmin.mockResolvedValue([personality()]);
  createPersonality.mockResolvedValue(personality());
  updatePersonality.mockResolvedValue(personality());
  deletePersonality.mockResolvedValue(undefined);
  translatePersonality.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AdminPersonalitiesSection — listing', () => {
  it('lists personalities ordered by sort_order', async () => {
    await renderLoaded([
      personality({ id: 'p2', code: 'zen', sort_order: 2 }),
      personality({ id: 'p1', code: 'coach', sort_order: 1 }),
    ]);
    const codes = screen.getAllByText(/^(coach|zen)$/).map(n => n.textContent);
    // `coach` (sort_order 1) must appear before `zen` (sort_order 2).
    expect(codes.indexOf('coach')).toBeLessThan(codes.indexOf('zen'));
  });

  it('reports a load failure', async () => {
    fetchPersonalitiesAdmin.mockRejectedValue(new Error('500'));
    render();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(`${I18N}.errors.loading`));
  });
});

describe('AdminPersonalitiesSection — protected default', () => {
  it('hides both destructive affordances on the default row', async () => {
    await renderLoaded([personality({ is_default: true })]);
    // The default personality can neither be deleted nor re-promoted: the UI
    // removes the affordances entirely (`handleDelete`'s `delete_default` guard
    // is defence in depth, unreachable from the interface).
    expect(screen.queryByRole('button', { name: `${TIP}.delete` })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: `${TIP}.set_default` })).not.toBeInTheDocument();
  });

  it('still offers them on a non-default row', async () => {
    await renderLoaded([personality({ is_default: false })]);
    expect(screen.getByRole('button', { name: `${TIP}.delete` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `${TIP}.set_default` })).toBeInTheDocument();
  });
});

describe('AdminPersonalitiesSection — row actions', () => {
  it('deletes a non-default personality once confirmed and refreshes', async () => {
    // W4b: the destructive path now goes through the in-app dialog, so the
    // test presses the confirming button instead of stubbing window.confirm.
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: `${TIP}.delete` }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(deletePersonality).toHaveBeenCalledWith('p1'));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.success.deleted`);
    // The list is re-read after the mutation (initial + refresh).
    await waitFor(() => expect(fetchPersonalitiesAdmin).toHaveBeenCalledTimes(2));
  });

  it('does not delete when the confirmation is dismissed', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: `${TIP}.delete` }));
    await answerConfirmDialog(user, false);
    expect(deletePersonality).not.toHaveBeenCalled();
  });

  it('surfaces the server message when a delete is refused', async () => {
    deletePersonality.mockRejectedValue(new Error('personality is in use'));
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: `${TIP}.delete` }));
    await answerConfirmDialog(user);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('personality is in use'));
  });

  it('promotes a non-default personality to default', async () => {
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: `${TIP}.set_default` }));
    await waitFor(() => expect(updatePersonality).toHaveBeenCalledWith('p1', { is_default: true }));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.success.set_default`);
  });

  it('generates translations and surfaces the server message on failure', async () => {
    translatePersonality.mockRejectedValue(new Error('quota exceeded'));
    const { user } = await renderLoaded();
    await user.click(screen.getByRole('button', { name: `${TIP}.generate_translations` }));
    await waitFor(() => expect(translatePersonality).toHaveBeenCalledWith('p1'));
    expect(toast.error).toHaveBeenCalledWith('quota exceeded');
  });
});
