/**
 * DocumentSettings — how LIA illustrates and animates the documents it creates.
 *
 * Two native radio groups showing the stored choices, a choice persisted
 * through the generic profile update then refreshed and toasted, the no-op
 * re-selection, the failure that changes nothing, a second choice refused while
 * one is saved WITHOUT disabling the focused control, and the note saying no
 * document is illustrated while the instance offers no image generation or the
 * person's own is off — the instance named first, never before `/config` answers.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import type { User } from '@/lib/auth';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
const { useAppConfig } = vi.hoisted(() => ({ useAppConfig: vi.fn() }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));
const { patch } = vi.hoisted(() => ({ patch: vi.fn() }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { patch },
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

import { DocumentSettings } from '../DocumentSettings';

const PREFIX = 'settings.documents';
const OPTION = (group: string, choice: string) => `${PREFIX}.${group}.options.${choice}.label`;

function authed(over: Partial<User> = {}) {
  return {
    user: makeUser({
      id: 'u1',
      document_illustrations: 'auto',
      document_animations: 'presented',
      image_generation_enabled: true,
      ...over,
    }),
    refreshUser: vi.fn().mockResolvedValue(true),
  };
}

/** The configuration `/config` answers, image generation offered or not by the operator. */
function instance(imagesOffered: boolean) {
  return {
    config: { capabilities: { image_generation: { enabled: imagesOffered, family: 'media' } } },
    loading: false,
    error: null,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue({});
  useAppConfig.mockReturnValue(instance(true));
});

describe('DocumentSettings', () => {
  it('offers both questions as named radio groups, the stored choices checked', () => {
    useAuth.mockReturnValue(authed({ document_animations: 'never' }));
    renderWithProviders(<DocumentSettings lng="en" />);

    const illustrations = screen.getByRole('group', { name: `${PREFIX}.illustrations.label` });
    const animations = screen.getByRole('group', { name: `${PREFIX}.animations.label` });
    expect(within(illustrations).getAllByRole('radio')).toHaveLength(3);
    expect(within(animations).getAllByRole('radio')).toHaveLength(3);
    expect(screen.getByRole('radio', { name: OPTION('illustrations', 'auto') })).toBeChecked();
    expect(screen.getByRole('radio', { name: OPTION('animations', 'never') })).toBeChecked();
    expect(screen.getByRole('radio', { name: OPTION('animations', 'presented') })).not.toBeChecked();
  });

  it('describes each group and each option with its own sentence', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<DocumentSettings lng="en" />);

    expect(screen.getByRole('group', { name: `${PREFIX}.illustrations.label` })).toHaveAccessibleDescription(
      `${PREFIX}.illustrations.hint`
    );
    for (const choice of ['auto', 'on_request', 'never']) {
      expect(
        screen.getByRole('radio', { name: OPTION('illustrations', choice) })
      ).toHaveAccessibleDescription(`${PREFIX}.illustrations.options.${choice}.description`);
    }
  });

  it('a new choice is stored on the profile, re-read and confirmed', async () => {
    const ctx = authed();
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<DocumentSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('illustrations', 'never') }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/users/u1',
        { document_illustrations: 'never' },
        undefined
      )
    );
    expect(ctx.refreshUser).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(`${PREFIX}.updated`);
  });

  it('re-choosing the stored option sends nothing', async () => {
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<DocumentSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('animations', 'presented') }));

    expect(patch).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('a failed save says so and leaves the stored choice selected', async () => {
    patch.mockRejectedValueOnce(new Error('offline'));
    const ctx = authed();
    useAuth.mockReturnValue(ctx);
    const { user } = renderWithProviders(<DocumentSettings lng="en" />);

    await user.click(screen.getByRole('radio', { name: OPTION('animations', 'always') }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('common.error'));
    expect(ctx.refreshUser).not.toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: OPTION('animations', 'presented') })).toBeChecked();
  });

  it('a second choice while one is saved is refused, and the focus stays where it was', async () => {
    let release: (value: unknown) => void = () => undefined;
    patch.mockReturnValueOnce(new Promise(resolve => (release = resolve)));
    useAuth.mockReturnValue(authed());
    const { user } = renderWithProviders(<DocumentSettings lng="en" />);

    const never = screen.getByRole('radio', { name: OPTION('illustrations', 'never') });
    await user.click(never);
    const group = screen.getByRole('group', { name: `${PREFIX}.animations.label` });
    await waitFor(() => expect(group).toHaveAttribute('aria-disabled', 'true'));
    const always = screen.getByRole('radio', { name: OPTION('animations', 'always') });
    await user.click(always);

    expect(patch).toHaveBeenCalledTimes(1);
    // Refused by the guard, never by disabling: the clicked control keeps the focus.
    expect(always).not.toBeDisabled();
    expect(always).toHaveFocus();
    expect(always).not.toBeChecked();
    expect(never).not.toBeDisabled();
    release({});
    await waitFor(() => expect(group).not.toHaveAttribute('aria-disabled'));
  });

  it('says no document is illustrated while image generation is off', () => {
    useAuth.mockReturnValue(authed({ image_generation_enabled: false }));
    renderWithProviders(<DocumentSettings lng="en" />);
    expect(screen.getByRole('note')).toHaveTextContent(`${PREFIX}.illustrations.needs_images`);
  });

  it('says nothing about images while they are on', () => {
    useAuth.mockReturnValue(authed());
    renderWithProviders(<DocumentSettings lng="en" />);
    expect(screen.queryByRole('note')).toBeNull();
  });

  it('says the instance offers no image, whatever the person switched on', () => {
    useAppConfig.mockReturnValue(instance(false));
    useAuth.mockReturnValue(authed());
    renderWithProviders(<DocumentSettings lng="en" />);
    expect(screen.getByRole('note')).toHaveTextContent(
      `${PREFIX}.illustrations.instance_without_images`
    );
  });

  it('names the instance alone when both are off: the person cannot reopen it', () => {
    useAppConfig.mockReturnValue(instance(false));
    useAuth.mockReturnValue(authed({ image_generation_enabled: false }));
    renderWithProviders(<DocumentSettings lng="en" />);
    const notes = screen.getAllByRole('note');
    expect(notes).toHaveLength(1);
    expect(notes[0]).toHaveTextContent(`${PREFIX}.illustrations.instance_without_images`);
  });

  it('states no absence before the configuration answers', () => {
    useAppConfig.mockReturnValue({ config: null, loading: true, error: null });
    useAuth.mockReturnValue(authed());
    renderWithProviders(<DocumentSettings lng="en" />);
    expect(screen.queryByRole('note')).toBeNull();
  });
});
