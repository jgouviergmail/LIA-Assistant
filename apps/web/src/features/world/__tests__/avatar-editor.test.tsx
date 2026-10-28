import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import { WorldAvatarEditor } from '../WorldAvatarEditor';
import { DEFAULT_AVATAR, type AvatarView, type AvatarWrite } from '../avatar-protocol';
import { AVATAR_PRESETS } from '../avatar-presets';

vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../WorldAvatarPreview', () => ({
  WorldAvatarPreview: () => <div role="img" aria-label="preview" />,
}));
const owner = '11111111-1111-4111-8111-111111111111';
const initial: AvatarView = {
  owner_id: owner,
  public_name: 'LIA account name',
  needs_setup: true,
  needs_reset: false,
  preferences: { version: 1, revision: 0, appearance: DEFAULT_AVATAR },
};
it('previews every preset without publishing, allows custom edits and saves through the existing revision contract', async () => {
  const save = vi.fn(async (write: AvatarWrite) => ({
    ...initial,
    preferences: { ...initial.preferences, appearance: write.appearance },
  }));
  render(
    <WorldAvatarEditor
      lng="en"
      initial={{ ...initial, needs_setup: false }}
      saving={false}
      save={save}
      refresh={vi.fn()}
      onSaved={vi.fn()}
    />
  );
  const picker = screen.getByRole('combobox', { name: 'world.avatar.presets.label' });
  for (const preset of AVATAR_PRESETS) {
    fireEvent.change(picker, { target: { value: preset.id } });
    expect(screen.getByRole('combobox', { name: 'world.avatar.hair' })).toHaveValue(
      preset.appearance.hair
    );
    expect(save).not.toHaveBeenCalled();
  }
  fireEvent.change(screen.getByRole('combobox', { name: 'world.avatar.skin' }), {
    target: { value: 'porcelain' },
  });
  expect(picker).toHaveValue('custom');
  fireEvent.click(screen.getByRole('button', { name: 'world.home.save' }));
  await waitFor(() => expect(save).toHaveBeenCalledOnce());
  expect(save.mock.calls[0][0]).toMatchObject({
    expected_revision: 0,
    appearance: { ...AVATAR_PRESETS[9].appearance, skin: 'porcelain' },
    consent: true,
  });
  expect(save.mock.calls[0][0]).not.toHaveProperty('preset');
});
it('keeps the focused save control reachable and freezes edits while saving', () => {
  const props = {
    lng: 'en' as const,
    initial,
    onboarding: true,
    saving: false,
    save: vi.fn(),
    refresh: vi.fn(),
    onSaved: vi.fn(),
  };
  const view = render(<WorldAvatarEditor {...props} />);
  fireEvent.click(screen.getByRole('checkbox'));
  const save = screen.getByRole('button', { name: 'world.session.enter' });
  save.focus();
  view.rerender(<WorldAvatarEditor {...props} saving />);
  expect(save).toHaveFocus();
  expect(save).not.toBeDisabled();
  expect(save).toHaveAttribute('aria-disabled', 'true');
  fireEvent.click(save);
  expect(props.save).not.toHaveBeenCalled();
  const hair = screen.getByRole('combobox', { name: 'world.avatar.hair' });
  expect(hair).not.toBeDisabled();
  fireEvent.change(hair, { target: { value: 'long' } });
  expect(hair).toHaveValue(initial.preferences.appearance.hair);
});
it('uses the server name, requires consent on first entry and submits only declared appearance', async () => {
  const saved = vi.fn();
  const save = vi.fn(async (write: AvatarWrite) => ({
    ...initial,
    needs_setup: false,
    preferences: { version: 1 as const, revision: 1, appearance: write.appearance },
  }));
  render(
    <WorldAvatarEditor
      lng="en"
      initial={initial}
      onboarding
      saving={false}
      save={save}
      refresh={async () => {}}
      onSaved={saved}
    />
  );
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.getByText(initial.public_name)).toBeInTheDocument();
  const enter = screen.getByRole('button', { name: 'world.session.enter' });
  expect(enter).toBeDisabled();
  fireEvent.change(screen.getByRole('combobox', { name: 'world.avatar.hair' }), {
    target: { value: 'long' },
  });
  fireEvent.click(screen.getByRole('checkbox', { name: 'world.session.consent' }));
  fireEvent.click(enter);
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  const write = save.mock.calls[0][0];
  expect(write.appearance.hair).toBe('long');
  expect(Object.keys(write).sort()).toEqual([
    'appearance',
    'consent',
    'expected_revision',
    'reset',
  ]);
});
it('ignores completion after the editor leaves', async () => {
  let finish!: (value: AvatarView) => void;
  const save = vi.fn(
    () =>
      new Promise<AvatarView>(resolve => {
        finish = resolve;
      })
  );
  const saved = vi.fn();
  const view = render(
    <WorldAvatarEditor
      lng="en"
      initial={initial}
      onboarding
      saving={false}
      save={save}
      refresh={async () => {}}
      onSaved={saved}
    />
  );
  fireEvent.click(screen.getByRole('checkbox', { name: 'world.session.consent' }));
  fireEvent.click(screen.getByRole('button', { name: 'world.session.enter' }));
  view.unmount();
  finish(initial);
  await Promise.resolve();
  expect(saved).not.toHaveBeenCalled();
});

it('preserves the rejected draft on a CAS conflict and explicitly reloads without retrying the write', async () => {
  const save = vi.fn().mockRejectedValue(new ApiError('stale', 409));
  const refresh = vi.fn(async () => {});
  render(
    <WorldAvatarEditor
      lng="en"
      initial={{ ...initial, needs_setup: false }}
      saving={false}
      save={save}
      refresh={refresh}
      onSaved={vi.fn()}
    />
  );
  const hair = screen.getByRole('combobox', { name: 'world.avatar.hair' });
  fireEvent.change(hair, { target: { value: 'long' } });
  fireEvent.click(screen.getByRole('button', { name: 'world.home.save' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('world.avatar.conflict');
  expect(hair).toHaveValue('long');
  fireEvent.click(screen.getByRole('button', { name: 'world.home.reload' }));
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
  expect(save).toHaveBeenCalledTimes(1);
});
