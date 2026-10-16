/**
 * EyesStyleSettings — registry-driven style picker.
 *
 * The option list must come from the eye-style registry (adding a style there
 * must surface here untouched), selection must persist through the widget
 * store, and every card must expose its translated accessible name plus the
 * two live previews carrying the style's data attribute.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EyesStyleSettings } from '../EyesStyleSettings';
import {
  EYE_STYLE_IDS,
  HYBRID_EYE_STYLE_IDS,
  RIG_EYE_STYLE_IDS,
  DEFAULT_EYE_STYLE,
} from '@/components/eyes/eye-styles';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { installSpiritBrowser } from '@/components/spirit/__tests__/browser';
import { activeFrameSubscribers } from '@/components/eyes/rig/scheduler';

beforeEach(() => {
  localStorage.removeItem(EYES_WIDGET_PREFS_KEY);
  useEyesWidgetStore.getState().reset();
  document.cookie = 'lia_gender=female; path=/';
  installSpiritBrowser();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('EyesStyleSettings', () => {
  it.each(RIG_EYE_STYLE_IDS.filter(style => style !== 'smiley'))(
    'persists %s and pauses its monitor previews outside hover',
    styleId => {
      render(<EyesStyleSettings lng="en" />);
      const option = screen.getByRole('button', { name: `eyes.styles.${styleId}.name` });
      expect(option.querySelectorAll('.lia-monitor-screen')).toHaveLength(2);
      expect(activeFrameSubscribers()).toBe(0);
      fireEvent.mouseEnter(option);
      expect(activeFrameSubscribers()).toBe(2);
      fireEvent.click(option);
      expect(option).toHaveAttribute('aria-current', 'true');
      expect(useEyesWidgetStore.getState().style).toBe(styleId);
      expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toContain(`"style":"${styleId}"`);
      fireEvent.mouseLeave(option);
      expect(activeFrameSubscribers()).toBe(0);
    }
  );
  it.each(['smiley', ...HYBRID_EYE_STYLE_IDS] as const)(
    'offers %s and restores its persisted selection',
    async id => {
      render(<EyesStyleSettings lng="en" />);
      const spirit = screen.getByRole('button', { name: `eyes.styles.${id}.name` });
      fireEvent.click(spirit);
      expect(useEyesWidgetStore.getState().style).toBe(id);
      expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toContain(`"style":"${id}"`);
      expect(spirit).toHaveAttribute('aria-current', 'true');
      const saved = localStorage.getItem(EYES_WIDGET_PREFS_KEY)!;
      cleanup();
      useEyesWidgetStore.getState().reset();
      localStorage.setItem(EYES_WIDGET_PREFS_KEY, saved);
      await useEyesWidgetStore.persist.rehydrate();
      expect(useEyesWidgetStore.getState().style).toBe(id);
      render(<EyesStyleSettings lng="en" />);
      expect(screen.getByRole('button', { name: `eyes.styles.${id}.name` })).toHaveAttribute(
        'aria-current',
        'true'
      );
    }
  );

  it.each(['smiley', ...HYBRID_EYE_STYLE_IDS])(
    'keeps both %s variants static until their option is hovered or focused',
    id => {
      render(<EyesStyleSettings lng="en" />);
      const spirit = screen.getByRole('button', { name: `eyes.styles.${id}.name` });
      const motion = () =>
        [...spirit.querySelectorAll('.lia-eyes')].map(face => face.getAttribute('data-motion'));
      const baseline = activeFrameSubscribers();
      expect(motion()).toEqual(['off', 'off']);
      fireEvent.mouseEnter(spirit);
      expect(motion()).toEqual([null, null]);
      expect(activeFrameSubscribers()).toBe(baseline + 2);
      fireEvent.mouseLeave(spirit);
      expect(motion()).toEqual(['off', 'off']);
      expect(activeFrameSubscribers()).toBe(baseline);
      fireEvent.focus(spirit);
      expect(motion()).toEqual([null, null]);
      expect(activeFrameSubscribers()).toBe(baseline + 2);
      fireEvent.blur(spirit);
      expect(motion()).toEqual(['off', 'off']);
      expect(activeFrameSubscribers()).toBe(baseline);
    }
  );

  it.each(['male', 'female'])(
    'presents female and male spirit variants independently of the %s preference',
    selectedGender => {
      document.cookie = `lia_gender=${selectedGender}; path=/`;
      render(<EyesStyleSettings lng="fr" />);
      const spirit = screen.getByRole('button', { name: 'eyes.styles.spirit.name' });
      expect(spirit.querySelectorAll('[data-spirit-companion="female"]')).toHaveLength(1);
      expect(spirit.querySelectorAll('[data-spirit-companion="male"]')).toHaveLength(1);
      expect(spirit).toHaveTextContent('eyes.variants.female');
      expect(spirit).toHaveTextContent('eyes.variants.male');
      expect(spirit.querySelectorAll('.lia-eye-shape')).toHaveLength(4);
      expect(spirit.querySelectorAll('img')).toHaveLength(0);
    }
  );

  it('shows neutral feminine and masculine Smiley portraits without changing the saved preference', () => {
    document.cookie = 'lia_gender=male; path=/';
    useEyesWidgetStore.getState().setStyle('moss');
    render(<EyesStyleSettings lng="fr" />);
    const option = screen.getByRole('button', { name: 'eyes.styles.smiley.name' });
    expect(option).toHaveTextContent('eyes.variants.female');
    expect(option).toHaveTextContent('eyes.variants.male');
    const portraits = [...option.querySelectorAll('.lia-eyes')];
    expect(portraits.map(face => face.getAttribute('data-smiley-variant'))).toEqual([
      'female',
      'male',
    ]);
    expect(portraits.map(face => face.getAttribute('data-expression'))).toEqual([
      'neutral',
      'neutral',
    ]);
    expect(useEyesWidgetStore.getState().style).toBe('moss');
    expect(document.cookie).toContain('lia_gender=male');
    expect(activeFrameSubscribers()).toBe(0);
  });

  it('renders one accessible option per registry style', () => {
    render(<EyesStyleSettings lng="en" />);
    for (const id of EYE_STYLE_IDS) {
      expect(screen.getByRole('button', { name: `eyes.styles.${id}.name` })).toBeInTheDocument();
    }
  });

  it('each option carries two live previews with the style data attribute', () => {
    render(<EyesStyleSettings lng="en" />);
    for (const id of EYE_STYLE_IDS) {
      const option = screen.getByRole('button', { name: `eyes.styles.${id}.name` });
      const previews = option.querySelectorAll(`[data-style='${id}']`);
      expect(previews).toHaveLength(2);
    }
  });

  it('keeps the previews COMPARABLE: no mimic, no sketch on a preview', () => {
    // A preview exists to compare silhouettes; a sneeze mid-comparison is
    // not a comparison. The breath and the hold stay — they are the pose.
    render(<EyesStyleSettings lng="en" />);
    const previews = document.querySelectorAll('.lia-eyes');
    expect(previews.length).toBeGreaterThan(0);
    previews.forEach(preview => expect(preview).toHaveAttribute('data-life', 'off'));
  });

  it('selecting a style persists it through the widget store', () => {
    render(<EyesStyleSettings lng="en" />);
    expect(useEyesWidgetStore.getState().style).toBe(DEFAULT_EYE_STYLE);
    fireEvent.click(screen.getByRole('button', { name: 'eyes.styles.anneaux.name' }));
    expect(useEyesWidgetStore.getState().style).toBe('anneaux');
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toContain('"style":"anneaux"');
  });

  it('shows the persisted avatar and updates its summary when the choice changes', () => {
    useEyesWidgetStore.getState().setStyle('moss');
    render(<EyesStyleSettings lng="en" />);
    const current = screen.getByRole('region', { name: 'settings.eyes_style.current' });
    expect(within(current).getByRole('heading', { name: 'eyes.styles.moss.name' })).toBeVisible();
    expect(current).toHaveTextContent('eyes.styles.moss.description');
    fireEvent.click(screen.getByRole('button', { name: 'eyes.styles.billes.name' }));
    expect(within(current).getByRole('heading', { name: 'eyes.styles.billes.name' })).toBeVisible();
    expect(current).not.toHaveTextContent('eyes.styles.moss.description');
    expect(
      screen.getAllByRole('button').filter(button => button.getAttribute('aria-current') === 'true')
    ).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'eyes.styles.billes.name' })).toHaveAttribute(
      'aria-current',
      'true'
    );
  });

  it('keeps keyboard selection focused and does not rewrite the saved current choice', async () => {
    const user = userEvent.setup();
    render(<EyesStyleSettings lng="en" />);
    const option = screen.getByRole('button', { name: 'eyes.styles.anneaux.name' });
    act(() => option.focus());
    await user.keyboard('{Enter}');
    expect(option).toHaveFocus();
    expect(option).toHaveAttribute('aria-current', 'true');
    expect(useEyesWidgetStore.getState().style).toBe('anneaux');
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    await user.keyboard(' ');
    expect(option).toHaveFocus();
    expect(writes).not.toHaveBeenCalled();
  });
});
