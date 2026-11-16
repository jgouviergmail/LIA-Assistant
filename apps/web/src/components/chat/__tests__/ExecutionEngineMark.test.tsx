/**
 * The mark under an AUTOMATIC answer (ADR-390): which engine produced it,
 * said in the person's language — and nothing at all under an answer whose
 * mode the person chose, or under a value no engine names.
 */
import { createInstance } from 'i18next';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { ExecutionEngineMark } from '../ExecutionEngineMark';

const language = createInstance();
await language.init({ lng: 'en', resources: { en: { translation: en }, fr: { translation: fr } } });
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: language.t, i18n: language }) }));

describe('ExecutionEngineMark', () => {
  it.each([
    ['react', 'ReAct', '.lucide-zap', 'Automatic mode: answered by the ReAct loop'],
    ['pipeline', 'Pipeline', '.lucide-workflow', 'Automatic mode: answered by a Pipeline plan'],
  ] as const)('names the %s engine in words and in a sentence', async (engine, word, glyph, said) => {
    await language.changeLanguage('en');
    const { container } = renderWithProviders(
      <ExecutionEngineMark metadata={{ execution_engine: engine }} />
    );

    const mark = screen.getByText(word).closest('[data-execution-engine]');
    expect(mark).toHaveAttribute('data-execution-engine', engine);
    // Hover says the whole sentence; a screen reader hears it instead of the bare word.
    expect(mark).toHaveAttribute('title', said);
    expect(screen.getByText(said)).toHaveClass('sr-only');
    expect(screen.getByText(word)).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector(glyph)).not.toBeNull();
  });

  it('is separated from the time by a bar that wraps with it', async () => {
    await language.changeLanguage('en');
    const { container } = renderWithProviders(
      <ExecutionEngineMark metadata={{ execution_engine: 'pipeline' }} />
    );

    // « 13:26 | Pipeline »: the bar belongs to the mark, so a phone that must
    // wrap carries « | Pipeline » to the next line whole.
    const bar = screen.getByText('|');
    expect(bar).toHaveAttribute('aria-hidden', 'true');
    const group = bar.parentElement;
    expect(group).toHaveClass('whitespace-nowrap');
    expect(group).toContainElement(container.querySelector('[data-execution-engine]'));
  });

  it('speaks the reader’s language', async () => {
    await language.changeLanguage('fr');
    renderWithProviders(<ExecutionEngineMark metadata={{ execution_engine: 'react' }} />);

    expect(
      screen.getByText('Mode automatique : réponse produite par la boucle ReAct')
    ).toBeInTheDocument();
  });

  it.each([
    ['a chosen mode', {}],
    ['no metadata', undefined],
    ['a requested mode, never an engine', { execution_engine: 'auto' }],
    ['a value of another shape', { execution_engine: 7 }],
  ])('says nothing under %s', (_case, metadata) => {
    const { container } = renderWithProviders(<ExecutionEngineMark metadata={metadata} />);

    expect(container).toBeEmptyDOMElement();
  });
});
