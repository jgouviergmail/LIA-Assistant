/**
 * Separator — what the wrapper decides (audit AC-040: it re-entered the
 * coverage measure): decorative by default, so assistive technology skips it;
 * a semantic separator announces its orientation; each orientation draws its
 * own hairline.
 */

import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { Separator } from '../separator';

describe('Separator', () => {
  it('is decorative and horizontal by default: no role a reader announces', () => {
    const { container } = renderWithProviders(<Separator />);
    const line = container.querySelector('[data-orientation]');

    expect(line).toHaveAttribute('role', 'none');
    expect(line).toHaveAttribute('data-orientation', 'horizontal');
    expect(line).toHaveClass('h-[1px]', 'w-full');
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  });

  it('announces a semantic separator, with its vertical orientation', () => {
    renderWithProviders(<Separator decorative={false} orientation="vertical" />);
    const line = screen.getByRole('separator');

    expect(line).toHaveAttribute('aria-orientation', 'vertical');
    expect(line).toHaveClass('h-full', 'w-[1px]');
  });
});
