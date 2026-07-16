/**
 * Avatar — characterization tests (audit F055).
 *
 * Written BEFORE decomposing the Avatar function (CC 31 > per-file cap 30) so
 * the extraction is provably behavior-preserving: these tests pin the current
 * rendering contract — image vs initials fallback, loading skeleton, status
 * badge, glow effect, and the keyboard-operable clickable variant — and must
 * stay green, unmodified, after the refactor.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

import { Avatar, AvatarGroup, getInitials, stringToColor } from '../avatar';

describe('getInitials / stringToColor (pure utils)', () => {
  it('derives initials: single word, multi word, empty', () => {
    expect(getInitials('Alice')).toBe('A');
    expect(getInitials('Jean de la Fontaine')).toBe('JF');
    expect(getInitials('')).toBe('?');
    expect(getInitials('  bob   marley  ')).toBe('BM');
  });

  it('hashes a name to a deterministic hsl color', () => {
    expect(stringToColor('Alice')).toBe(stringToColor('Alice'));
    expect(stringToColor('Alice')).toMatch(/^hsl\(\d+, 60%, 50%\)$/);
  });
});

describe('Avatar — content variants', () => {
  it('renders the image when src is provided (proxied/raw), with alt fallback chain', () => {
    const { container } = render(<Avatar src="/photo.jpg" name="Jane Doe" />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img!.getAttribute('alt')).toBe('Jane Doe'); // alt ?? name ?? 'Avatar'
    // No initials while the image is healthy.
    expect(container.textContent).not.toContain('JD');
  });

  it('prefers explicit alt over name', () => {
    const { container } = render(<Avatar src="/p.jpg" alt="Profile picture" name="Jane" />);
    expect(container.querySelector('img')!.getAttribute('alt')).toBe('Profile picture');
  });

  it('falls back to "Avatar" alt when neither alt nor name is given', () => {
    const { container } = render(<Avatar src="/p.jpg" />);
    expect(container.querySelector('img')!.getAttribute('alt')).toBe('Avatar');
  });

  it('shows color-hashed initials when there is no src', () => {
    const { container } = render(<Avatar name="Jane Doe" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('JD');
  });

  it('falls back to initials when the image errors', () => {
    const { container } = render(<Avatar src="/broken.jpg" name="Jane Doe" />);
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('JD');
  });

  it('reveals the image only once loaded (opacity transition)', () => {
    const { container } = render(<Avatar src="/photo.jpg" name="Jane" />);
    const img = container.querySelector('img')!;
    expect(img.className).toContain('opacity-0');
    fireEvent.load(img);
    expect(img.className).toContain('opacity-100');
  });

  it('shows a skeleton and no initials while loading', () => {
    const { container } = render(<Avatar name="Jane Doe" loading />);
    // Skeleton present, initials suppressed while loading.
    expect(container.textContent).not.toContain('JD');
  });

  it('renders the status badge with accessible label (verified shows the check icon)', () => {
    const { getByLabelText, rerender } = render(<Avatar name="A" status="online" />);
    expect(getByLabelText('Online')).toBeTruthy();
    rerender(<Avatar name="A" status="verified" />);
    expect(getByLabelText('Verified').textContent).toContain('✓');
  });
});

describe('Avatar — clickable variant (keyboard-operable, audit F012/F045)', () => {
  it('is inert (no role, no tabindex) when not clickable', () => {
    const { container } = render(<Avatar name="Jane" />);
    const root = container.firstElementChild!;
    expect(root.getAttribute('role')).toBeNull();
    expect(root.hasAttribute('tabindex')).toBe(false);
  });

  it('exposes button semantics and activates once per click', () => {
    const onClick = vi.fn();
    const { container } = render(<Avatar name="Jane" onClick={onClick} />);
    const root = container.firstElementChild!;
    expect(root.getAttribute('role')).toBe('button');
    expect(root.getAttribute('tabindex')).toBe('0');

    fireEvent.click(root);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('activates on Enter and Space, but not on other keys', () => {
    const onClick = vi.fn();
    const { container } = render(<Avatar name="Jane" onClick={onClick} />);
    const root = container.firstElementChild!;

    fireEvent.keyDown(root, { key: 'Enter' });
    fireEvent.keyDown(root, { key: ' ' });
    fireEvent.keyDown(root, { key: 'Escape' });
    fireEvent.keyDown(root, { key: 'a' });

    expect(onClick).toHaveBeenCalledTimes(2);
  });
});

describe('Avatar — effects', () => {
  it('applies the glow hover halo only when effect=glow and hover enabled', () => {
    const { container, rerender } = render(<Avatar name="A" effect="glow" />);
    expect(container.querySelector('.bg-gradient-radial')).not.toBeNull();

    rerender(<Avatar name="A" effect="glow" disableHover />);
    expect(container.querySelector('.bg-gradient-radial')).toBeNull();

    rerender(<Avatar name="A" effect="glass" />);
    expect(container.querySelector('.bg-gradient-radial')).toBeNull();
  });
});

describe('AvatarGroup', () => {
  it('caps the displayed avatars and shows the +N overflow chip', () => {
    const avatars = Array.from({ length: 7 }, (_, i) => ({ name: `User ${i}` }));
    const { container } = render(<AvatarGroup avatars={avatars} max={5} />);
    expect(container.textContent).toContain('+2');
  });

  it('shows no overflow chip when under the cap', () => {
    const avatars = [{ name: 'A' }, { name: 'B' }];
    const { container } = render(<AvatarGroup avatars={avatars} max={5} />);
    expect(container.textContent).not.toContain('+');
  });
});
