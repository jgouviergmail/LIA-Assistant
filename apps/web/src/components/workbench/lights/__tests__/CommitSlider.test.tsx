/**
 * CommitSlider (ADR-369): a range is SENT on release. A pointer releases once;
 * a key steps the value and the browser fires `change` at every step — a key
 * held down must still send once, when it is released, or one drag of the
 * thumb by keyboard would be a request per step against the bridge's window.
 */

import { fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';

import { CommitSlider } from '../CommitSlider';

function slider(onCommit = vi.fn(() => Promise.resolve())) {
  renderWithProviders(
    <CommitSlider
      label="Brightness"
      value={50}
      min={0}
      max={100}
      format={value => `${value} %`}
      onCommit={onCommit}
    />
  );
  return { range: screen.getByRole('slider', { name: 'Brightness' }), onCommit };
}

describe('CommitSlider — a word on the screen, more for the ear', () => {
  it('shows the short word and names the room to the ear', () => {
    renderWithProviders(
      <CommitSlider
        label="Brightness"
        name="Brightness of Kitchen"
        value={40}
        min={0}
        max={100}
        format={value => `${value} %`}
        onCommit={() => Promise.resolve()}
      />
    );

    expect(screen.getByText('Brightness')).toBeVisible();
    expect(screen.getByRole('slider', { name: 'Brightness of Kitchen' })).toBeInTheDocument();
  });
});

describe('CommitSlider', () => {
  it('sends the released value once', async () => {
    const { range, onCommit } = slider();

    fireEvent.input(range, { target: { value: '40' } });
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.change(range, { target: { value: '40' } });

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(40);
    await waitFor(() => expect(range).toHaveValue('50'));
  });

  it('sends a key held down once, when the key is released', async () => {
    const { range, onCommit } = slider();

    fireEvent.keyDown(range, { key: 'ArrowRight' });
    for (const value of ['51', '52', '53']) {
      fireEvent.change(range, { target: { value } });
    }
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.keyUp(range, { key: 'ArrowRight' });

    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith(53);
    await waitFor(() => expect(range).toHaveValue('50'));
  });

  it('sends nothing for a key that moved nothing', () => {
    const { range, onCommit } = slider();

    fireEvent.keyDown(range, { key: 'Tab' });
    fireEvent.keyUp(range, { key: 'Tab' });

    expect(onCommit).not.toHaveBeenCalled();
  });
});
