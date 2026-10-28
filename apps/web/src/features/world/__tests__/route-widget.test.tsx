import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { WorldExplorationControls } from '../WorldExplorationControls';
import type { WorldExperienceControl } from '../useWorldExperiencePreferences';
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
function control(overrides: Partial<WorldExperienceControl> = {}): WorldExperienceControl {
  return {
    experience: {
      owner_id: 'owner',
      needs_reset: false,
      preferences: {
        version: 1,
        revision: 2,
        show_route: true,
        season_mode: 'calendar',
        hemisphere: 'north',
      },
    },
    loading: false,
    failed: false,
    saving: false,
    save: vi.fn(async () => true),
    refresh: vi.fn(async () => {}),
    reload: vi.fn(async () => true),
    ...overrides,
  };
}
it('keeps route focus and its committed value while a preference write is pending', () => {
  const state = control();
  const props = { lng: 'fr' as const, exploration: { control: state, enabled: true } };
  const ui = render(<WorldExplorationControls {...props} />);
  const button = screen.getByRole('button', { name: 'world.experience.route' });
  button.focus();
  fireEvent.click(button);
  expect(state.save).toHaveBeenCalledWith({ expected_revision: 2, show_route: false });
  ui.rerender(
    <WorldExplorationControls
      {...props}
      exploration={{ ...props.exploration, control: { ...state, saving: true } }}
    />
  );
  expect(button).toHaveAttribute('aria-disabled', 'true');
  expect(button).toHaveFocus();
  expect(button).toHaveAttribute('aria-pressed', 'true');
  fireEvent.click(button);
  expect(state.save).toHaveBeenCalledTimes(1);
  expect(screen.queryByText('world.experience.discover')).not.toBeInTheDocument();
});
it('clears a failed write only after a re-read lands, with touch-sized recovery actions', async () => {
  const state = control({ save: vi.fn(async () => false), reload: vi.fn(async () => false) });
  render(<WorldExplorationControls lng="en" exploration={{ control: state, enabled: true }} />);
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'world.experience.route' }));
  });
  expect(screen.getByRole('status')).toHaveTextContent('world.experience.failed');
  const retry = screen.getByRole('button', { name: 'world.retry' });
  expect(retry).toHaveClass('min-h-11');
  await act(async () => {
    fireEvent.click(retry);
  });
  expect(state.reload).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('status')).toHaveTextContent('world.experience.failed');
  vi.mocked(state.reload).mockResolvedValueOnce(true);
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'world.retry' }));
  });
  expect(state.reload).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
it('offers a touch-sized repair for an unreadable document and keeps its focus while saving', () => {
  const base = control();
  if (!base.experience) throw new Error('fixture');
  const broken = { ...base, experience: { ...base.experience, needs_reset: true } };
  const ui = render(
    <WorldExplorationControls lng="en" exploration={{ control: broken, enabled: true }} />
  );
  const repair = screen.getByRole('button', { name: 'world.experience.repair' });
  expect(repair).toHaveClass('min-h-11');
  repair.focus();
  fireEvent.click(repair);
  expect(broken.save).toHaveBeenCalledExactlyOnceWith({ expected_revision: 2, reset: true });
  ui.rerender(
    <WorldExplorationControls
      lng="en"
      exploration={{ control: { ...broken, saving: true }, enabled: true }}
    />
  );
  expect(repair).toHaveAttribute('aria-disabled', 'true');
  expect(repair).toHaveFocus();
  fireEvent.click(repair);
  expect(broken.save).toHaveBeenCalledTimes(1);
});
