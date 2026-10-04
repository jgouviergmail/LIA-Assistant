import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const references: { id: string; language: string; html: string }[] = JSON.parse(
  readFileSync(
    join(process.cwd(), '../api/tests/unit/domains/agents/display/card_reference_corpus.json'),
    'utf8'
  )
);
const reference = references.find(item => item.id === 'weather_details' && item.language === 'en');
if (!reference) throw new Error('Missing backend weather fixture');
const html = reference.html;

describe('weather reading selection in archived messages', () => {
  it('keeps exclusive native selection within each message, even with identical item identifiers', () => {
    const { container } = render(
      <>
        <MarkdownContent content={html} />
        <MarkdownContent content={html} />
      </>
    );
    const groups = container.querySelectorAll('.lia-weather-series');
    const names = [...groups].map(group =>
      [...group.querySelectorAll('details.lia-weather-slot')].map(slot => slot.getAttribute('name'))
    );
    expect(names[0]).toHaveLength(3);
    expect(new Set(names[0]).size).toBe(1);
    expect(names[0][0]).toBeTruthy();
    expect(names[0][0]).not.toBe(names[1][0]);
    expect(container.textContent).toContain('1008 hPa');
    expect(container.querySelectorAll('table tbody tr')).toHaveLength(6);
  });

  it('reveals every matching slot for history search instead of letting native exclusivity hide matches', () => {
    const { container } = render(<MarkdownContent content={html} searchHighlight="1008" />);
    const slots = container.querySelectorAll('details.lia-weather-slot');
    expect(slots).toHaveLength(3);
    for (const slot of slots) {
      expect(slot).toHaveAttribute('open');
      expect(slot).not.toHaveAttribute('name');
    }
    expect(container.querySelector('table')).toBeInTheDocument();
  });
});
