import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { WorldSessionDialog } from '../WorldSessionDialog';
import type { SessionPresentation } from '../useWorldSession';
const base: SessionPresentation = {
  connection: 'online',
  admission: 'absent',
  controlling: false,
  position: null,
  offer: null,
  zone: 'arrival',
  participants: [],
  nearbyParticipants: [],
  pose: null,
  epoch: null,
};
it('offers explicit readmission for an expired presence instead of an ineffective controller takeover', () => {
  const accept = vi.fn(),
    takeover = vi.fn();
  render(
    <WorldSessionDialog
      lng="en"
      presentation={base}
      open
      onLeave={vi.fn()}
      onAccept={accept}
      onTakeover={takeover}
    />
  );
  expect(screen.getByRole('heading', { name: 'world.session.expired' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'world.session.takeover' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'world.session.rejoin' }));
  expect(accept).toHaveBeenCalledTimes(1);
  expect(takeover).not.toHaveBeenCalled();
});
it('retains explicit takeover only for a still-present account controlled elsewhere', () => {
  render(
    <WorldSessionDialog
      lng="en"
      presentation={{ ...base, admission: 'active' }}
      open
      onLeave={vi.fn()}
      onAccept={vi.fn()}
      onTakeover={vi.fn()}
    />
  );
  expect(screen.getByRole('button', { name: 'world.session.takeover' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'world.session.rejoin' })).not.toBeInTheDocument();
});
