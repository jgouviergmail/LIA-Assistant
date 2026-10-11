import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import { SelectedCompanionPortrait } from '../SelectedCompanionPortrait';
import { activeFrameSubscribers } from '@/components/eyes/rig/scheduler';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';

beforeEach(() => installSpiritBrowser());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Spirit portraits use the same current body as the companion', () => {
  it.each(['female', 'male'] as const)(
    'paints the %s native historical face on v2 without a GPU or clock',
    variant => {
      const { container } = render(
        <SelectedCompanionPortrait
          styleId="spirit"
          variant={variant}
          expression="sad"
          animate={false}
        />
      );
      const body = container.querySelector('[data-character="spirit"]');
      expect(body).toHaveAttribute('data-spirit-companion', variant);
      expect(body).toHaveStyle({
        '--spirit-body-url': `url('/avatars/spirit/v2/${variant}/body.webp')`,
      });
      const face = container.querySelector('.lia-eyes');
      expect(face).toHaveAttribute('data-expression', 'sad');
      expect(face).toHaveAttribute('data-motion', 'off');
      expect(face).toHaveAttribute('data-life', 'off');
      expect(container.querySelector('[data-rig-mouth]')?.getAttribute('d')).toBeTruthy();
      expect(container.querySelectorAll('.lia-eye-pupil-clip > .lia-eye-pupil')).toHaveLength(2);
      expect(container.querySelectorAll('canvas, img')).toHaveLength(0);
      expect(activeFrameSubscribers()).toBe(0);
    }
  );
});
