/**
 * AvatarVariantPicker — the hero's visible avatar affordance.
 *
 * The whole hero image is (and remains) a click target that flips the avatar.
 * That affordance is invisible, so the change could read as accidental. This
 * picker shows the two portraits side by side: the reader CHOOSES one instead
 * of flipping blind, and can see what each choice produces.
 *
 * Two oracles matter here and neither is a CSS assertion:
 *  - which variant is announced as pressed, and what a click actually selects;
 *  - that the programmatic names resolve from the locale rather than being
 *    hardcoded (checked against the real `en` and `fr` dictionaries).
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import enDict from '../../../../locales/en/translation.json';
import frDict from '../../../../locales/fr/translation.json';
import { AvatarVariantPicker } from '../AvatarVariantPicker';

vi.mock('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    <span data-testid="thumb" data-src={src}>
      {alt}
    </span>
  ),
}));

const VARIANTS = { female: '/LIA_TC.jpg', male: '/LIA_TCM.jpg' };

function makeProps(over: Partial<React.ComponentProps<typeof AvatarVariantPicker>> = {}) {
  return {
    isMale: false,
    mounted: true,
    variants: VARIANTS,
    onSelect: vi.fn(),
    ...over,
  };
}

describe('AvatarVariantPicker — choosing rather than flipping', () => {
  it('offers both portraits as named buttons inside a named group', () => {
    renderWithProviders(<AvatarVariantPicker {...makeProps()} />);

    expect(
      screen.getByRole('group', { name: 'dashboard.avatar_picker.group_label' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'dashboard.avatar_picker.female' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'dashboard.avatar_picker.male' })
    ).toBeInTheDocument();
  });

  it('announces which variant is active', () => {
    renderWithProviders(<AvatarVariantPicker {...makeProps({ isMale: true })} />);

    expect(screen.getByRole('button', { name: 'dashboard.avatar_picker.male' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByRole('button', { name: 'dashboard.avatar_picker.female' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
  });

  it('selects the requested variant — not a blind flip', async () => {
    const onSelect = vi.fn();
    const { user } = renderWithProviders(<AvatarVariantPicker {...makeProps({ onSelect })} />);

    // Already on female: pressing female must still SELECT female, so the
    // control is idempotent instead of toggling under the reader.
    await user.click(screen.getByRole('button', { name: 'dashboard.avatar_picker.female' }));
    expect(onSelect).toHaveBeenLastCalledWith(false);

    await user.click(screen.getByRole('button', { name: 'dashboard.avatar_picker.male' }));
    expect(onSelect).toHaveBeenLastCalledWith(true);
  });

  it('is operable with the keyboard', async () => {
    const onSelect = vi.fn();
    const { user } = renderWithProviders(<AvatarVariantPicker {...makeProps({ onSelect })} />);

    await user.tab();
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'dashboard.avatar_picker.female' })
    );
    await user.tab();
    const male = screen.getByRole('button', { name: 'dashboard.avatar_picker.male' });
    expect(document.activeElement).toBe(male);

    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledWith(true);
  });

  it('claims no active variant before the cookie has been read', () => {
    // Server render and first paint do not know the preference yet; asserting
    // "female is pressed" then would state a preference nobody expressed.
    renderWithProviders(<AvatarVariantPicker {...makeProps({ mounted: false })} />);

    expect(
      screen.getByRole('button', { name: 'dashboard.avatar_picker.female' })
    ).not.toHaveAttribute('aria-pressed');
  });

  it('shows the portrait each button selects', () => {
    renderWithProviders(<AvatarVariantPicker {...makeProps()} />);

    const thumbs = screen.getAllByTestId('thumb');
    expect(thumbs.map(t => t.getAttribute('data-src'))).toEqual([VARIANTS.female, VARIANTS.male]);
  });

  it('leaves the thumbnails out of the accessibility tree — the button is named', () => {
    // A described image inside a named button would be announced twice.
    renderWithProviders(<AvatarVariantPicker {...makeProps()} />);

    expect(screen.getAllByTestId('thumb').every(t => t.textContent === '')).toBe(true);
  });
});

describe('AvatarVariantPicker — the names come from the locale', () => {
  const KEYS = ['group_label', 'female', 'male'] as const;

  it.each([
    ['en', enDict],
    ['fr', frDict],
  ])('%s resolves every programmatic name to real text', (_lng, dict) => {
    const picker = (dict as { dashboard: { avatar_picker?: Record<string, string> } }).dashboard
      .avatar_picker;
    expect(picker).toBeDefined();
    for (const key of KEYS) {
      expect(picker?.[key]).toBeTruthy();
      // Not the key echoed back, and not an untranslated placeholder.
      expect(picker?.[key]).not.toContain('avatar_picker');
    }
  });

  it('distinguishes the two portraits — identical names would be unusable', () => {
    for (const dict of [enDict, frDict]) {
      const picker = (dict as { dashboard: { avatar_picker?: Record<string, string> } }).dashboard
        .avatar_picker;
      expect(picker?.female).not.toBe(picker?.male);
    }
  });
});
