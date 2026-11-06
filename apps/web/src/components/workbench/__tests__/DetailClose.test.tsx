/**
 * The way out of a detail (ADR-369): where it stands beside the list a cross, where it takes the
 * screen the place it goes back to, and the same element under the focus a tool gives it.
 */
import { createRef } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { width } = vi.hoisted(() => ({ width: { desktop: false } }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => width.desktop }));

import { DetailClose } from '../DetailClose';

afterEach(() => {
  width.desktop = false;
});

function draw(onClose = vi.fn(), buttonRef = createRef<HTMLButtonElement>()) {
  const rendered = renderWithProviders(
    <DetailClose
      closeLabel="Close the file"
      backLabel="Files"
      onClose={onClose}
      buttonRef={buttonRef}
    />
  );
  return { ...rendered, onClose, buttonRef };
}

describe('DetailClose', () => {
  it('says where it goes back to when the detail takes the screen', async () => {
    const { user, onClose } = draw();

    await user.click(screen.getByRole('button', { name: 'Files' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('is a cross with a name beside the list', async () => {
    width.desktop = true;
    const { user, onClose } = draw();

    await user.click(screen.getByRole('button', { name: 'Close the file' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it.each([true, false])('hands its element to the tool (beside the list: %s)', desktop => {
    width.desktop = desktop;
    const { buttonRef } = draw();

    expect(buttonRef.current).toBe(screen.getByRole('button'));
  });
});
