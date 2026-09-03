/**
 * The minutes structure editor: add, reorder, remove, rename — the key stays
 * stable once assigned, and the last section cannot be removed.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
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

describe('MeetingTemplateEditor — readable sections (ADR-259)', () => {
  it('folds the instruction by default behind a named disclosure with a one-line preview', async () => {
    const { user } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={vi.fn()} />
    );
    const toggles = screen.getAllByRole('button', { name: 'meetings.settings.instruction_toggle' });
    expect(toggles).toHaveLength(2);
    expect(toggles[0]).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText('meetings.settings.section_instruction')).toBeNull();
    expect(screen.getByText('Prose.')).toBeInTheDocument();
    await user.click(toggles[0]);
    expect(toggles[0]).toHaveAttribute('aria-expanded', 'true');
    const textarea = screen.getByLabelText('meetings.settings.section_instruction');
    expect(textarea).toHaveValue('Prose.');
    const panel = document.getElementById(toggles[0].getAttribute('aria-controls') ?? '');
    expect(panel).toContainElement(textarea);
  });

  it('opens a freshly added section and focuses its instruction', async () => {
    const onChange = vi.fn();
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={onChange} />
    );
    await user.click(screen.getByRole('button', { name: 'meetings.settings.add_section' }));
    const next = onChange.mock.calls[0][0] as TemplateSection[];
    rerender(<MeetingTemplateEditor lng="en" sections={next} onChange={onChange} />);
    const toggles = screen.getAllByRole('button', { name: 'meetings.settings.instruction_toggle' });
    expect(toggles[2]).toHaveAttribute('aria-expanded', 'true');
    const textarea = screen.getByLabelText('meetings.settings.section_instruction');
    await waitFor(() => expect(textarea).toHaveFocus());
  });

  it('flags a collapsed section whose instruction is empty', () => {
    const empty: TemplateSection[] = [
      { key: 'summary', label: 'Résumé', instruction: '', kind: 'paragraph' },
      { key: 'decisions', label: 'Décisions', instruction: 'Puces.', kind: 'bullets' },
    ];
    renderWithProviders(<MeetingTemplateEditor lng="en" sections={empty} onChange={vi.fn()} />);
    // An empty instruction is required work: the section opens itself and says so.
    const toggles = screen.getAllByRole('button', { name: 'meetings.settings.instruction_toggle' });
    expect(toggles[0]).toHaveAttribute('aria-expanded', 'true');
    expect(toggles[1]).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('meetings.settings.instruction_missing')).toBeInTheDocument();
    expect(screen.getByLabelText('meetings.settings.section_instruction')).toHaveAttribute(
      'aria-invalid',
      'true'
    );
  });

  it('keeps the panel open while the first characters of an empty instruction are typed', async () => {
    const empty: TemplateSection[] = [
      { key: 'summary', label: 'Résumé', instruction: '', kind: 'paragraph' },
    ];
    const onChange = vi.fn();
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={empty} onChange={onChange} />
    );
    const textarea = screen.getByLabelText('meetings.settings.section_instruction');
    await user.type(textarea, 'P');
    const next = onChange.mock.calls.at(-1)?.[0] as TemplateSection[];
    expect(next[0].instruction).toBe('P');
    rerender(<MeetingTemplateEditor lng="en" sections={next} onChange={onChange} />);
    // The section is no longer "required work", yet it must not fold under the user's fingers.
    expect(screen.getByLabelText('meetings.settings.section_instruction')).toHaveValue('P');
    expect(
      screen.getByRole('button', { name: 'meetings.settings.instruction_toggle' })
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('cannot fold an empty instruction, and typing after that attempt keeps it open', async () => {
    const empty: TemplateSection[] = [
      { key: 'summary', label: 'Résumé', instruction: '', kind: 'paragraph' },
    ];
    const onChange = vi.fn();
    const { user, rerender } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={empty} onChange={onChange} />
    );
    const toggle = screen.getByRole('button', { name: 'meetings.settings.instruction_toggle' });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.type(screen.getByLabelText('meetings.settings.section_instruction'), 'P');
    const next = onChange.mock.calls.at(-1)?.[0] as TemplateSection[];
    rerender(<MeetingTemplateEditor lng="en" sections={next} onChange={onChange} />);
    expect(
      screen.getByRole('button', { name: 'meetings.settings.instruction_toggle' })
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('toggles the disclosure from the keyboard', async () => {
    const { user } = renderWithProviders(
      <MeetingTemplateEditor lng="en" sections={sections()} onChange={vi.fn()} />
    );
    const [toggle] = screen.getAllByRole('button', {
      name: 'meetings.settings.instruction_toggle',
    });
    toggle.focus();
    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});
