import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { WorldSeasonControls } from '../WorldSeasonControls';
import type { WorldExperienceControl } from '../useWorldExperiencePreferences';
const control = (): WorldExperienceControl => ({
  experience: {
    owner_id: '11111111-1111-4111-8111-111111111111',
    needs_reset: false,
    preferences: {
      version: 1,
      revision: 7,
      show_route: true,
      season_mode: 'calendar',
      hemisphere: 'north',
    },
  },
  loading: false,
  failed: false,
  saving: false,
  save: vi.fn(async () => true),
  refresh: vi.fn(),
  reload: vi.fn(),
});
it('saves explicit seasonal choices with the existing revision and surfaces a rejected write', async () => {
  const state = control();
  const view = render(<WorldSeasonControls lng="en" control={state} enabled />);
  fireEvent.change(screen.getByRole('combobox', { name: 'world.seasons.mode' }), {
    target: { value: 'winter' },
  });
  await waitFor(() =>
    expect(state.save).toHaveBeenCalledWith({ expected_revision: 7, season_mode: 'winter' })
  );
  vi.mocked(state.save).mockResolvedValueOnce(false);
  fireEvent.change(screen.getByRole('combobox', { name: 'world.seasons.hemisphere' }), {
    target: { value: 'south' },
  });
  expect(await screen.findByRole('status')).toHaveTextContent('world.experience.failed');
  vi.mocked(state.save).mockRejectedValueOnce(new Error('offline'));
  fireEvent.change(screen.getByRole('combobox', { name: 'world.seasons.mode' }), {
    target: { value: 'off' },
  });
  await waitFor(() => expect(state.save).toHaveBeenCalledTimes(3));
  expect(screen.getByRole('status')).toHaveTextContent('world.experience.failed');
  view.rerender(<WorldSeasonControls lng="en" control={state} enabled={false} />);
  fireEvent.change(screen.getByRole('combobox', { name: 'world.seasons.mode' }), {
    target: { value: 'spring' },
  });
  expect(state.save).toHaveBeenCalledTimes(3);
});
it.each(['mode', 'hemisphere'] as const)(
  'keeps the focused %s select reachable while a write is pending and refuses its change',
  field => {
    const state = control();
    const view = render(<WorldSeasonControls lng="en" control={state} enabled />);
    const select = screen.getByRole('combobox', { name: 'world.seasons.' + field });
    select.focus();
    view.rerender(<WorldSeasonControls lng="en" control={{ ...state, saving: true }} enabled />);
    expect(select).not.toBeDisabled();
    expect(select).toHaveAttribute('aria-disabled', 'true');
    expect(select).toHaveFocus();
    fireEvent.change(select, { target: { value: field === 'mode' ? 'winter' : 'south' } });
    expect(state.save).not.toHaveBeenCalled();
    expect(select).toHaveValue(field === 'mode' ? 'calendar' : 'north');
    view.rerender(<WorldSeasonControls lng="en" control={state} enabled />);
    expect(select).toHaveAttribute('aria-disabled', 'false');
    expect(select).toHaveFocus();
  }
);
