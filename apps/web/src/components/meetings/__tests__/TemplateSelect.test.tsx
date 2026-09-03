/**
 * The shared template picker (ADR-259): grouped by category in library order,
 * an optional « automatic » first entry, and the chosen name on the trigger.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingTemplateSummary } from '@/types/meetings';

import { AUTO_TEMPLATE, TemplateSelect } from '../TemplateSelect';

function summary(over: Partial<MeetingTemplateSummary> = {}): MeetingTemplateSummary {
  return {
    ref: 'builtin:default_minutes',
    name: 'Meeting minutes',
    description: null,
    category: 'meeting',
    builtin: true,
    sections_count: 6,
    auto_selectable: true,
    ...over,
  };
}

const TEMPLATES = [summary(), summary({ ref: 'user:1', name: 'Mine', category: 'custom' })];

describe('TemplateSelect', () => {
  it('names the chosen template on the labelled trigger', () => {
    renderWithProviders(
      <TemplateSelect
        lng="en"
        id="pick"
        label="Format"
        templates={TEMPLATES}
        value="user:1"
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox', { name: 'Format' })).toHaveTextContent('Mine');
  });

  it('states the automatic choice when offered and nothing is chosen', () => {
    renderWithProviders(
      <TemplateSelect
        lng="en"
        id="pick"
        label="Format"
        templates={TEMPLATES}
        value={null}
        autoLabel="Automatic"
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox', { name: 'Format' })).toHaveTextContent('Automatic');
    expect(AUTO_TEMPLATE).toBe('auto');
  });

  it('sets the category headings apart from the items with their glyph and an indent', async () => {
    const { user } = renderWithProviders(
      <TemplateSelect
        lng="en"
        id="pick"
        label="Format"
        templates={TEMPLATES}
        value="user:1"
        onChange={vi.fn()}
      />
    );
    await user.click(screen.getByRole('combobox', { name: 'Format' }));
    const heading = await screen.findByText('meetings.templates.category.meeting');
    expect(heading.querySelector('svg')).not.toBeNull();
    const option = screen.getByRole('option', { name: 'Meeting minutes' });
    expect(option.className).toContain('pl-9');
    expect(heading.className).toContain('text-primary');
  });

  it('states a placeholder when nothing is chosen and no automatic entry exists', () => {
    renderWithProviders(
      <TemplateSelect
        lng="en"
        id="pick"
        label="Format"
        templates={TEMPLATES}
        value={null}
        placeholder="Choose a format"
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox', { name: 'Format' })).toHaveTextContent('Choose a format');
  });
});
