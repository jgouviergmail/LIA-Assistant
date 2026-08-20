/**
 * EyesStyleSettings — registry-driven style picker.
 *
 * The option list must come from the eye-style registry (adding a style there
 * must surface here untouched), selection must persist through the widget
 * store, and every card must expose its translated accessible name plus the
 * two live previews carrying the style's data attribute.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { EyesStyleSettings } from '../EyesStyleSettings';
import { EYE_STYLE_IDS, DEFAULT_EYE_STYLE } from '@/components/eyes/eye-styles';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';

beforeEach(() => {
  localStorage.removeItem(EYES_WIDGET_PREFS_KEY);
  useEyesWidgetStore.getState().reset();
});

describe('EyesStyleSettings', () => {
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
      const previews = option.querySelectorAll(`.lia-eyes[data-style='${id}']`);
      expect(previews).toHaveLength(2);
    }
  });

  it('selecting a style persists it through the widget store', () => {
    render(<EyesStyleSettings lng="en" />);
    expect(useEyesWidgetStore.getState().style).toBe(DEFAULT_EYE_STYLE);
    fireEvent.click(screen.getByRole('button', { name: 'eyes.styles.anneaux.name' }));
    expect(useEyesWidgetStore.getState().style).toBe('anneaux');
    expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toContain('"style":"anneaux"');
  });

  it('marks the selected option (and only it) with the primary ring', () => {
    render(<EyesStyleSettings lng="en" />);
    fireEvent.click(screen.getByRole('button', { name: 'eyes.styles.billes.name' }));
    const selected = screen.getByRole('button', { name: 'eyes.styles.billes.name' });
    const other = screen.getByRole('button', { name: 'eyes.styles.cozmo.name' });
    expect(selected.className).toContain('border-primary');
    expect(other.className).not.toContain('border-primary');
  });
});
