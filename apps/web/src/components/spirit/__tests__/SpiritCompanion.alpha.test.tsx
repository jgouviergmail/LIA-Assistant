import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { SpiritCompanion } from '../SpiritCompanion';
import { installSpiritBrowser } from './browser';
import { COMPANION_BODY_ALPHA_FLOOR } from '../companion-catalogue';
import { sourceAlphaTransfer } from '@/components/eyes/volume/source-alpha';

beforeEach(() => installSpiritBrowser());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('the fallback source-alpha material', () => {
  it('owns one unique local filter per companion and releases it with the instance', () => {
    const props = {
      variant: 'female',
      animate: false,
      expression: 'neutral',
      gaze: null,
      life: false,
      size: 'sm',
    } as const;
    const first = render(<SpiritCompanion {...props} character="bip" />);
    const second = render(<SpiritCompanion {...props} character="oscar" />);
    const filter = first.container.querySelector('filter')!;
    const other = second.container.querySelector('filter')!;
    expect(filter.id).not.toBe(other.id);
    expect(first.container.querySelector('[data-character]')).toHaveStyle({
      '--spirit-body-alpha-filter': `url("#${filter.id}")`,
    });
    expect(filter).toHaveAttribute('color-interpolation-filters', 'sRGB');
    const alpha = filter.querySelector('feFuncA')!;
    const transfer = sourceAlphaTransfer(COMPANION_BODY_ALPHA_FLOOR);
    expect(alpha).toHaveAttribute('type', 'linear');
    expect(Number(alpha.getAttribute('slope'))).toBe(transfer.slope);
    expect(Number(alpha.getAttribute('intercept'))).toBe(transfer.intercept);
    expect(filter.querySelectorAll('feFuncR, feFuncG, feFuncB')).toHaveLength(0);
    const svg = filter.closest('svg')!;
    expect(svg).toHaveAttribute('width', '0');
    expect(svg).toHaveAttribute('height', '0');
    expect(svg).toHaveStyle({ position: 'absolute' });
    expect(svg.style.display).not.toBe('none');
    first.rerender(<SpiritCompanion {...props} character="moss" variant="male" />);
    expect(first.container.querySelector('filter')?.id).toBe(filter.id);
    first.unmount();
    expect(document.getElementById(filter.id)).toBeNull();
    expect(document.getElementById(other.id)).toBe(other);
  });
});
