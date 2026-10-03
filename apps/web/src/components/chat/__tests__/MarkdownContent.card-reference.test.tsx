/** The backend reference contract survives the real Markdown sanitizer. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

interface Reference {
  id: string;
  language: string;
  html: string;
}

const references: Reference[] = JSON.parse(
  readFileSync(
    join(process.cwd(), '../api/tests/unit/domains/agents/display/card_reference_corpus.json'),
    'utf8'
  )
);

const domainFacts: Record<string, string[]> = {
  mcps: ['MCP_LAST_DESCRIPTION', 'Alternate received title', 'MCP_LAST_NESTED', 'Received field 8'],
  weathers: ['18°C'],
  emails: ['Votre réservation est confirmée.'],
  routes: ['Gare de Lyon Part-Dieu'],
  places: ['Le Jardin des Saveurs'],
  tasks: ['Dernière note : billets et confirmation.', 'Étape 13'],
  contacts: ['camille4@example.test'],
  events: ['participant13@example.test'],
  files: ["Dernière ligne : rendez-vous à l'accueil."],
  calendars: ['Voyage à Lyon'],
  hues: ['Lampe du bureau', '0%'],
  tickets: ['Préparer la visite', 'LIA'],
  wikipedia: ['LAST_ARTICLE_FACT', 'Category 6', 'Last supplied section'],
  perplexity: ['RECEIVED_QUESTION', 'RESEARCH_LAST_FACT', 'source8.example.test'],
  braves: ['LAST_NEWS_FACT', '2 hours ago'],
  web_search: ['LAST_UNIFIED_FACT_7', 'Related question 6'],
};

function expectedDomains(id: string): string[] {
  if (id === 'native_details') return ['hues', 'contacts', 'calendars', 'events', 'tickets'];
  if (id === 'microsoft') return ['tasks', 'events', 'calendars'];
  if (id === 'mcp_details') return ['mcps'];
  if (id === 'research_details') return ['wikipedia', 'perplexity', 'braves', 'web_search'];
  if (id === 'mixed') return ['weathers', 'emails', 'routes', 'places'];
  if (id === 'details') return ['tasks', 'contacts', 'events', 'files', 'calendars'];
  if (id === 'snapshots') return ['hues', 'tickets'];
  if (id === 'gallery') return ['places'];
  if (id === 'place_details') return ['places'];
  if (id === 'route_details') return ['routes'];
  if (id === 'weather_details') return ['weathers'];
  return [id];
}

function assertDomainFacts(reference: Reference, container: HTMLElement) {
  const domains = expectedDomains(reference.id);
  expect(container.querySelectorAll('.lia-card')).toHaveLength(domains.length);
  const text = container.textContent ?? '';
  if (reference.id === 'native_details') {
    for (const fact of [
      '4000 K',
      'Garden keeper',
      'Received pronunciation',
      '22 Garden Street',
      'garden@example.test',
      '0.3',
      '0.4',
      'Original garden',
      'My garden',
      'Alternate video',
      '123456',
      'LAST_DESCRIPTION',
      'LAST_COMMENT',
      'Step one',
      '0 €',
    ])
      expect(text).toContain(fact);
    expect(container.querySelector('meter')).toHaveAttribute('value', '0');
    expect(container.querySelector('meter')).toHaveAttribute('min', '0');
    expect(container.querySelector('meter')).toHaveAttribute('max', '100');
    expect(container.querySelector('meter')?.getAttribute('aria-label')).toBeTruthy();
    expect(text).not.toContain('PROVIDER_ID_NOT_DISPLAYED');
    return;
  }
  if (reference.id === 'microsoft') {
    for (const fact of [
      'Préparer la visite',
      'Design',
      'Accessibilité',
      'Visite du jardin',
      '12',
      'Calendrier de l’équipe',
    ]) {
      expect(text).toContain(fact);
    }
    expect(container.querySelector('progress')).toBeNull();
    return;
  }
  for (const domain of domains) {
    const facts =
      reference.id === 'weather_details'
        ? ['0°C', '2.4 m/s', '1008 hPa', '1.5 mm / 3 h']
        : reference.id === 'route_details'
          ? ['Place Bellecour', 'Gare de Vaise', 'M D', 'OTHER_RECEIVED_JOURNEY']
          : domainFacts[domain];
    for (const fact of facts) expect(text).toContain(fact);
  }
  const progress = container.querySelector('progress');
  if (domains.includes('tasks')) {
    expect(progress).toHaveAttribute('value', '6');
    expect(progress).toHaveAttribute('max', '13');
    expect(progress?.getAttribute('aria-label')).toBeTruthy();
  }
}

describe('backend card reference contract', () => {
  it.each(references)('$language $id keeps facts, safe links and native disclosures', reference => {
    const { container } = render(<MarkdownContent content={reference.html} />);
    assertDomainFacts(reference, container);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('[onclick], [onerror]')).toBeNull();
    expect(container.querySelector('[data-card-version="2"]')).not.toBeNull();
    for (const summary of container.querySelectorAll('summary')) {
      expect(summary.textContent?.trim().length).toBeGreaterThan(0);
      expect(summary.parentElement?.tagName).toBe('DETAILS');
    }
    for (const link of container.querySelectorAll('a')) {
      expect(link.getAttribute('href')).not.toMatch(/^javascript:/i);
    }
  });
});
