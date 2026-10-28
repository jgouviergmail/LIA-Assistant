import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { WorldDashboardOffer } from '../WorldDashboardOffer';
import { WorldSeatedDashboard } from '../WorldSeatedDashboard';
import { SeatDashboardIntent } from '../seat-dashboard-intent';

vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
it('declines or dismisses without opening data or asking the seated owner to stand', () => {
  const choose = vi.fn();
  const view = render(<WorldDashboardOffer lng="en" open onChoice={choose} />);
  fireEvent.click(screen.getByRole('button', { name: 'world.dashboard.stay' }));
  expect(choose).toHaveBeenCalledExactlyOnceWith(false);
  view.rerender(<WorldDashboardOffer lng="en" open onChoice={choose} />);
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape', code: 'Escape' });
  expect(choose.mock.calls.at(-1)).toEqual([false]);
});
it('opens only after the explicit affirmative choice', () => {
  const choose = vi.fn();
  render(<WorldDashboardOffer lng="en" open onChoice={choose} />);
  expect(choose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'world.dashboard.open' }));
  expect(choose).toHaveBeenCalledExactlyOnceWith(true);
});

it.each(['close', 'outside'] as const)('treats %s dismissal as refusal', async dismissal => {
  const choose = vi.fn();
  const user = userEvent.setup();
  render(<WorldDashboardOffer lng="en" open onChoice={choose} />);
  if (dismissal === 'close') await user.click(screen.getByRole('button', { name: 'common.close' }));
  else {
    const backdrop = document.querySelector('.lia-overlay-backdrop');
    if (!backdrop) throw new Error('Missing native modal backdrop');
    await user.click(backdrop);
  }
  expect(choose).toHaveBeenCalledExactlyOnceWith(false);
});

it('never presents a retained offer for a different authoritative seat', () => {
  const intent = new SeatDashboardIntent();
  intent.request('atrium-n:0');
  const accept = vi.fn();
  const view = render(
    <WorldSeatedDashboard
      lng="en"
      active
      seatKey="epoch:atrium-n:0"
      pose="atrium-n:0"
      offer={intent.getSnapshot()}
      intent={intent}
      onAccept={accept}
    />
  );
  expect(screen.getByRole('dialog')).toBeVisible();
  view.rerender(
    <WorldSeatedDashboard
      lng="en"
      active
      seatKey="epoch:atrium-s:0"
      pose="atrium-s:0"
      offer={intent.getSnapshot()}
      intent={intent}
      onAccept={accept}
    />
  );
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(accept).not.toHaveBeenCalled();
});
