import { createRef } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { BriefingTextRecovery } from '../BriefingTextRecovery';

it('keeps the retry and its focus while loading, then returns focus to the recovered briefing', async () => {
  const pending = Promise.withResolvers<void>();
  const retry = vi.fn(() => pending.promise);
  const heading = createRef<HTMLHeadingElement>();
  const recovered = () => heading.current?.focus();
  function Content({ unavailable, loading }: { unavailable: boolean; loading: boolean }) {
    return (
      <>
        <h2 ref={heading} tabIndex={-1}>
          Briefing
        </h2>
        <BriefingTextRecovery
          unavailable={unavailable}
          loading={loading}
          onRetry={retry}
          onRecovered={recovered}
        />
      </>
    );
  }
  const view = render(<Content unavailable loading={false} />);
  const button = screen.getByRole('button', { name: 'common.retry' });
  // Mouse activation does not focus buttons in WebKit by default.
  expect(button).not.toHaveFocus();
  expect(retry).not.toHaveBeenCalled();
  fireEvent.click(button);
  expect(button).toHaveFocus();
  expect(retry).toHaveBeenCalledOnce();
  view.rerender(<Content unavailable={false} loading />);
  expect(button).toHaveFocus();
  expect(button).toHaveAttribute('aria-busy', 'true');
  view.rerender(<Content unavailable={false} loading={false} />);
  await waitFor(() => expect(heading.current).toHaveFocus());
  await act(async () => pending.resolve());
});
it('never takes focus away from another deliberate destination', async () => {
  const recovered = vi.fn();
  const props = {
    unavailable: true,
    loading: false,
    onRetry: async () => {},
    onRecovered: recovered,
  };
  const view = render(
    <>
      <input aria-label="Another destination" />
      <BriefingTextRecovery {...props} />
    </>
  );
  fireEvent.click(screen.getByRole('button', { name: 'common.retry' }));
  screen.getByRole('textbox').focus();
  view.rerender(
    <>
      <input aria-label="Another destination" />
      <BriefingTextRecovery {...props} unavailable={false} />
    </>
  );
  await act(async () => {});
  expect(recovered).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox')).toHaveFocus();
});
