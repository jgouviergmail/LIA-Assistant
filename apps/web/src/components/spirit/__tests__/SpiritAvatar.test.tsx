import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { SpiritAvatar } from '../SpiritAvatar';
import { installSpiritBrowser, showSpirit, SpiritIntersectionObserver } from './browser';

let browser: ReturnType<typeof installSpiritBrowser>;
beforeEach(() => {
  browser = installSpiritBrowser();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('SpiritAvatar playback ownership', () => {
  it('keeps the compact bitmap when the display size changes', () => {
    const { container, rerender } = render(
      <SpiritAvatar variant="male" expression="joy" animate size={40} />
    );
    act(() => showSpirit(container));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy.webp'
    );
    rerender(<SpiritAvatar variant="male" expression="joy" animate size={41} />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy.webp'
    );
    expect(container.querySelector('img')).toHaveAttribute('width', '41');
    rerender(<SpiritAvatar variant="male" expression="joy" animate={false} size={114.4} />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy-still.webp'
    );
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/neutral-still.webp'
    );
    rerender(<SpiritAvatar variant="male" expression="joy" animate size={40} />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy.webp'
    );
  });

  it('loads only the still portrait until the avatar enters the viewport', () => {
    const { container } = render(
      <SpiritAvatar variant="female" expression="joy" animate size={40} />
    );
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/female/joy-still.webp'
    );
    act(() => showSpirit(container));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/female/joy.webp'
    );
    expect(container.querySelector('img')).toHaveAttribute('width', '40');
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true');
  });

  it('removes the animated image when offscreen or when playback is revoked', () => {
    const { container, rerender } = render(
      <SpiritAvatar variant="male" expression="thinking" animate />
    );
    act(() => showSpirit(container));
    const animated = container.querySelector('img');
    act(() => showSpirit(container, false));
    expect(animated).not.toBeInTheDocument();
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/thinking-still.webp'
    );
    act(() => showSpirit(container));
    rerender(<SpiritAvatar variant="male" expression="thinking" animate={false} />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/thinking-still.webp'
    );
  });

  it('never requests animation under reduced motion and follows preference changes', () => {
    browser.media.matches = true;
    const { container } = render(<SpiritAvatar variant="male" expression="joy" animate />);
    act(() => showSpirit(container));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy-still.webp'
    );
    act(() => browser.setMotion(false));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy.webp'
    );
    act(() => browser.setMotion(true));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy-still.webp'
    );
  });

  it('suspends decoding while the tab is hidden and resumes on return', () => {
    const { container } = render(<SpiritAvatar variant="female" expression="neutral" animate />);
    act(() => showSpirit(container));
    act(() => browser.setVisibility('hidden'));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/female/neutral-still.webp'
    );
    act(() => browser.setVisibility('visible'));
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/female/neutral.webp'
    );
  });

  it('shares browser listeners and releases them after the final avatar unmounts', () => {
    const first = render(<SpiritAvatar variant="female" expression="neutral" animate />);
    const second = render(<SpiritAvatar variant="male" expression="neutral" animate />);
    expect(browser.media.addEventListener).toHaveBeenCalledTimes(1);
    first.unmount();
    expect(browser.media.removeEventListener).not.toHaveBeenCalled();
    second.unmount();
    expect(browser.media.removeEventListener).toHaveBeenCalledTimes(1);
    expect(SpiritIntersectionObserver.instances[0].targets.size).toBe(0);
  });
});

describe('SpiritAvatar failure recovery', () => {
  it('falls back once to the still, then neutral, then LIA without retrying failed sources', () => {
    const { container, rerender } = render(
      <SpiritAvatar variant="male" expression="joy" animate />
    );
    act(() => showSpirit(container));
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/joy-still.webp'
    );
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/male/neutral-still.webp'
    );
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toBeNull();
    expect(container).toHaveTextContent('LIA');
    rerender(<SpiritAvatar variant="male" expression="joy" animate={false} />);
    rerender(<SpiritAvatar variant="male" expression="joy" animate />);
    expect(container.querySelector('img')).toBeNull();
    rerender(<SpiritAvatar variant="female" expression="joy" animate />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/female/joy.webp'
    );
  });

  it('can render the fixed portrait without IntersectionObserver', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    const { container } = render(<SpiritAvatar variant="female" expression="neutral" animate />);
    expect(container.querySelector('img')).toHaveAttribute(
      'src',
      '/avatars/spirit/v1/compact/female/neutral-still.webp'
    );
  });
});
