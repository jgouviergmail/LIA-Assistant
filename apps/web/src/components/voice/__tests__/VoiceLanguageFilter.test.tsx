/**
 * The voice pickers' language switch (ADR-345 amendment 2026-10-14): named by its
 * visible label, operable, and worded in the six languages with the reader's
 * language named in that language — key parity alone does not guarantee the
 * placeholder survives translation.
 */
import { describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';
import { languages } from '@/i18n/settings';
import { languageName } from '@/lib/language-name';

import { VoiceLanguageFilter } from '../VoiceLanguageFilter';

describe('VoiceLanguageFilter', () => {
  it('is a switch named by its label, and turning it off says so', () => {
    const onOnlyChange = vi.fn();
    renderWithProviders(<VoiceLanguageFilter lng="fr" only onOnlyChange={onOnlyChange} />);

    const only = screen.getByRole('switch', {
      name: 'settings.voice_language_filter.only_language',
    });
    expect(only).toBeChecked();
    fireEvent.click(only);
    expect(onOnlyChange).toHaveBeenCalledWith(false);
  });

  it.each(languages)('%s words it with the reader’s language named in it', async lng => {
    const bundle = (await import(`../../../../locales/${lng}/translation.json`)).default as {
      settings: { voice_language_filter: { only_language: string } };
    };
    const sentence = bundle.settings.voice_language_filter.only_language;

    expect(sentence.split('{{language}}')).toHaveLength(2);
    const named = languageName(lng, lng);
    expect(named).not.toBe(lng); // the browser names every language of the site
    expect(sentence.replace('{{language}}', named)).not.toContain('{{');
  });
});
