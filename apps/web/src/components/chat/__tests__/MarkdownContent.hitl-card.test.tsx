/**
 * MarkdownContent — the HITL confirmation card, as the backend now writes it.
 *
 * Since ADR-276 lot 14 the card is authored by the renderer and streamed
 * BEFORE the model's question: an emoji title, a Markdown list of fields, an
 * optional paragraph for a text, a `---` rule between two blank lines, then
 * the question. What capture 1 (2026-09-09) showed was the opposite shape —
 * fields spaced out as paragraphs and a `---` glued to a line, rendered as
 * three literal characters. This pins what the pipeline makes of the new one:
 * a real list, a real rule, no paragraph per field.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const CARD = [
  '📧 **Tout va bien**',
  '',
  '- **Destinataire** : marie.dupont@example.com',
  '- **Objet** : Tout va bien',
  '',
  '**Message**',
  '',
  'Bonjour,',
  '',
  'Je voulais juste te dire que tout va bien de mon côté.',
  '',
  'À bientôt,',
  '',
  '---',
  '',
  'Souhaitez-vous envoyer cet e-mail ?',
].join('\n');

describe('MarkdownContent — the HITL confirmation card', () => {
  it('renders the fields as ONE list, not a paragraph each', () => {
    const { container } = render(<MarkdownContent content={CARD} />);

    const lists = container.querySelectorAll('ul');
    expect(lists).toHaveLength(1);
    expect(lists[0].querySelectorAll('li')).toHaveLength(2);
    expect(lists[0].textContent).toContain('Destinataire');
    expect(lists[0].textContent).toContain('marie.dupont@example.com');
  });

  it('renders the rule as a rule, never as three characters', () => {
    const { container } = render(<MarkdownContent content={CARD} />);

    expect(container.querySelector('hr')).not.toBeNull();
    expect(container.textContent).not.toContain('---');
  });

  it('keeps the title bold under its emoji and the question last', () => {
    const { container } = render(<MarkdownContent content={CARD} />);

    const strong = container.querySelector('strong');
    expect(strong?.textContent).toBe('Tout va bien');
    expect(container.textContent?.trim().endsWith('Souhaitez-vous envoyer cet e-mail ?')).toBe(
      true
    );
  });

  it('gives the body its own paragraphs and nothing else a paragraph', () => {
    const { container } = render(<MarkdownContent content={CARD} />);

    const paragraphs = Array.from(container.querySelectorAll('p')).map(p => p.textContent);
    // Title, « Message » lead, three body paragraphs, the question: six — and
    // not one per field, which is what spread the old card down the screen.
    expect(paragraphs).toHaveLength(6);
    expect(paragraphs).not.toContain(expect.stringContaining('Destinataire'));
  });
});
