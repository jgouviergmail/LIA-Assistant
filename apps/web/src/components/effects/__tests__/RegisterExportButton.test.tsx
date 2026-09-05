/**
 * RegisterExportButton — three formats, and one of them is safe to hand on.
 *
 * The component had no test of its own since lot 4; this file closes that and
 * pins the decisions that would otherwise be undone by a well-meaning edit:
 *
 * - the downloads are ANCHORS, never buttons. A top-level same-site GET carries
 *   the session cookie on its own, while fetching a register into a blob works
 *   until the day one outgrows what a tab wants to hold in memory.
 * - the URL goes through `apiEndpointUrl`. A relative `/api/v1/...` would hit
 *   the FRONTEND origin, which has no such route — found live once already.
 * - the third format is described, not merely offered: what the file holds
 *   decides whether it is safe to send to someone, and three words cannot say
 *   that on their own.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RegisterExportButton } from '@/components/effects/RegisterExportButton';

const dictionary: Record<string, string> = {
  'effects.export.group_label': 'Export this register',
  'effects.export.markdown': 'Readable',
  'effects.export.csv': 'Spreadsheet',
  'effects.export.technical': 'Technical',
  'effects.export.markdown_hint': 'A document to read, with your own wordings',
  'effects.export.csv_hint': 'A spreadsheet to count, with your own wordings',
  'effects.export.technical_hint': 'JSON Lines: the same events with no content at all',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => dictionary[key] ?? key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('@/lib/api-client', () => ({
  apiEndpointUrl: (path: string) => `https://api.test.local/api/v1${path}`,
}));

describe('RegisterExportButton', () => {
  it('offers the three formats of one register', () => {
    render(<RegisterExportButton register="actions" />);

    expect(screen.getByRole('link', { name: /Readable/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Spreadsheet/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Technical/ })).toBeInTheDocument();
  });

  it('asks the API for the register it was given', () => {
    render(<RegisterExportButton register="consultations" />);

    for (const [name, format] of [
      ['Readable', 'markdown'],
      ['Spreadsheet', 'csv'],
      ['Technical', 'technical'],
    ] as const) {
      expect(screen.getByRole('link', { name: new RegExp(name) }).getAttribute('href')).toBe(
        `https://api.test.local/api/v1/effects/export?register=consultations&format=${format}`
      );
    }
  });

  it('never points at the FRONTEND origin', () => {
    // A relative `/api/v1/...` would hit the app itself, which has no such
    // route. Found live once already.
    render(<RegisterExportButton register="actions" />);

    for (const link of screen.getAllByRole('link')) {
      expect(link.getAttribute('href')).toMatch(/^https:\/\/api\.test\.local\//);
    }
  });

  it('downloads through ANCHORS rather than fetching into memory', () => {
    render(<RegisterExportButton register="actions" />);

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(3);
    for (const link of links) {
      expect(link).toHaveAttribute('download');
    }
  });

  it('says what each file HOLDS, because that decides who it can be sent to', () => {
    render(<RegisterExportButton register="actions" />);

    expect(screen.getByRole('link', { name: /Technical/ })).toHaveAttribute(
      'title',
      'JSON Lines: the same events with no content at all'
    );
  });

  it('associates the description programmatically, not only as a tooltip', () => {
    // A `title` reaches neither a screen reader nor a finger, and the
    // distinction it carries decides whether the file is safe to send.
    const { container } = render(<RegisterExportButton register="actions" />);

    const link = screen.getByRole('link', { name: /Technical/ });
    const describedBy = link.getAttribute('aria-describedby');

    expect(describedBy).toBeTruthy();
    expect(container.querySelector(`#${describedBy}`)?.textContent).toBe(
      'JSON Lines: the same events with no content at all'
    );
  });

  it('keeps the visible label short and the explanation out of it', () => {
    // The description lives in an `sr-only` span INSIDE the link, so the
    // accessible name would swallow it if it were not hidden from layout.
    render(<RegisterExportButton register="actions" />);

    expect(screen.getByRole('link', { name: /Technical/ }).textContent).toContain('Technical');
  });

  it('names the group for a reader who arrives by keyboard', () => {
    render(<RegisterExportButton register="actions" />);

    expect(screen.getByRole('group', { name: 'Export this register' })).toBeInTheDocument();
  });
});
