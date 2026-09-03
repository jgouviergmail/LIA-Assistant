/**
 * The minutes structure editor: add, reorder, remove, rename — the key stays
 * stable once assigned, and the last section cannot be removed.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { TemplateSection } from '@/types/meetings';

import { MAX_TEMPLATE_SECTIONS, MeetingTemplateEditor } from '../MeetingTemplateEditor';

function sections(): TemplateSection[] {
  return [
    { key: 'summary', label: 'Résumé', instruction: 'Prose.', kind: 'paragraph' },
    { key: 'decisions', label: 'Décisions', instruction: 'Puces.', kind: 'bullets' },
  ];
}

describe('MeetingTemplateEditor', () => {
  it('adds a section with a fresh unique key and the default bullets kind', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={onChange} />
    );
    await user.click(screen.getByRole('button', { name: 'meetings.settings.add_section' }));
    const next = onChange.mock.calls[0][0] as TemplateSection[];
    expect(next).toHaveLength(3);
    expect(next[2].kind).toBe('bullets');
    expect(next[2].key).toMatch(/^[a-z][a-z0-9_]{1,39}$/);
    expect(new Set(next.map(s => s.key)).size).toBe(3);
  });

  it('moves a section down and keeps every key', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={onChange} />
    );
    await user.click(screen.getAllByRole('button', { name: 'meetings.settings.move_down' })[0]);
    expect((onChange.mock.calls[0][0] as TemplateSection[]).map(s => s.key)).toEqual([
      'decisions',
      'summary',
    ]);
  });

  it('removes a section but never the last one', async () => {
    const onChange = vi.fn();
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={onChange} />
    );
    const removeButtons = screen.getAllByRole('button', {
      name: 'meetings.settings.remove_section',
    });
    await user.click(removeButtons[1]);
    expect((onChange.mock.calls[0][0] as TemplateSection[]).map(s => s.key)).toEqual(['summary']);

    onChange.mockClear();
    rerender(
      <MeetingTemplateEditor lng="en" sections={sections().slice(0, 1)} onChange={onChange} />
    );
    const lonely = screen.getByRole('button', { name: 'meetings.settings.remove_section' });
    expect(lonely).toHaveAttribute('aria-disabled', 'true');
    await user.click(lonely);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('renaming a heading keeps its key', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={onChange} />
    );
    const [label] = screen.getAllByLabelText('meetings.settings.section_label');
    await user.type(label, '!');
    const next = onChange.mock.calls.at(-1)?.[0] as TemplateSection[];
    expect(next[0].label).toBe('Résumé!');
    expect(next[0].key).toBe('summary');
  });

  it('refuses to add beyond the API bound and says so', async () => {
    const full: TemplateSection[] = Array.from({ length: MAX_TEMPLATE_SECTIONS }, (_, i) => ({
      key: `s${i}`,
      label: `S${i}`,
      instruction: 'i',
      kind: 'bullets',
    }));
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={full} onChange={onChange} />
    );
    const add = screen.getByRole('button', { name: 'meetings.settings.add_section' });
    expect(add).toHaveAttribute('aria-disabled', 'true');
    await user.click(add);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText('meetings.settings.max_sections')).toBeInTheDocument();
  });
});
