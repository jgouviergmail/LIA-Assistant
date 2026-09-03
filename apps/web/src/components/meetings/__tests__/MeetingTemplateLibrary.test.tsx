/**
 * The library (ADR-259, recomposed after the owner's review): two sections —
 * « My templates » first, the built-ins after — each grouped by category,
 * every category folded by default, empty categories absent. A built-in is
 * previewed or added to my templates (alone or as a selection); a user row is
 * previewed, edited, duplicated or deleted (alone or as a selection). Names
 * are asserted by key in the global stub; the six-locale gate owns the words.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import type { MeetingTemplateSummary } from '@/types/meetings';

import { MeetingTemplateLibrary } from '../MeetingTemplateLibrary';

function summary(over: Partial<MeetingTemplateSummary> = {}): MeetingTemplateSummary {
  return {
    ref: 'builtin:default_minutes',
    name: 'Meeting minutes',
    description: 'Summary, topics, decisions.',
    category: 'meeting',
    builtin: true,
    sections_count: 6,
    auto_selectable: true,
    ...over,
  };
}

const TEMPLATES: MeetingTemplateSummary[] = [
  summary(),
  summary({ ref: 'builtin:daily_standup', name: 'Daily standup', sections_count: 4 }),
  summary({
    ref: 'builtin:transcript_clean',
    name: 'Clean transcript',
    category: 'transcript',
    sections_count: 1,
    auto_selectable: false,
  }),
  summary({ ref: 'user:1', name: 'Mine', description: null, category: 'meeting', builtin: false }),
  summary({ ref: 'user:2', name: 'Retro', description: null, category: 'custom', builtin: false }),
];

function render(over: Partial<React.ComponentProps<typeof MeetingTemplateLibrary>> = {}) {
  const handlers = {
    onPreview: vi.fn(),
    onEdit: vi.fn(),
    onAddToMine: vi.fn(),
    onDuplicate: vi.fn(),
    onDelete: vi.fn(),
    onBrowse: vi.fn(),
  };
  const utils = renderWithProviders(
    <MeetingTemplateLibrary
      lng="en"
      templates={TEMPLATES}
      maxUserTemplates={50}
      busy={false}
      {...handlers}
      {...over}
    />
  );
  return { ...utils, ...handlers };
}

function section(name: string) {
  return screen.getByRole('region', { name });
}

describe('MeetingTemplateLibrary — structure', () => {
  it('shows my templates first, then the built-ins, each with its categories folded', () => {
    render();
    const mine = section('meetings.templates.mine_title');
    const builtins = section('meetings.templates.builtin_title');
    expect(mine.compareDocumentPosition(builtins) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // My templates: two categories (meeting, custom), custom first; none open.
    const mineTriggers = within(mine).getAllByRole('button', { expanded: false });
    expect(mineTriggers.map(b => b.textContent)).toEqual([
      expect.stringContaining('meetings.templates.category.custom'),
      expect.stringContaining('meetings.templates.category.meeting'),
    ]);
    expect(within(mine).queryByText('Mine')).not.toBeInTheDocument();

    // Built-ins: meeting and transcript only (no empty category), folded too.
    const builtinTriggers = within(builtins).getAllByRole('button', { expanded: false });
    expect(builtinTriggers.map(b => b.textContent)).toEqual([
      expect.stringContaining('meetings.templates.category.meeting'),
      expect.stringContaining('meetings.templates.category.transcript'),
    ]);
  });

  it('states the count of my templates against the cap and offers to browse when empty', async () => {
    const { user, onBrowse } = render({ templates: TEMPLATES.filter(t => t.builtin) });
    const mine = section('meetings.templates.mine_title');
    expect(within(mine).getByText('meetings.templates.mine_count')).toBeInTheDocument();
    await user.click(
      within(mine).getByRole('button', { name: 'meetings.templates.browse_builtins' })
    );
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });
});

describe('MeetingTemplateLibrary — rows and actions', () => {
  it('a built-in row offers preview and add-to-mine, never edit or delete', async () => {
    const { user, onPreview, onAddToMine } = render();
    const builtins = section('meetings.templates.builtin_title');
    await user.click(
      within(builtins).getByRole('button', { name: /meetings\.templates\.category\.meeting/ })
    );
    const row = within(builtins).getByRole('listitem', { name: 'Meeting minutes' });
    expect(within(row).getByText('meetings.templates.sections_count')).toBeInTheDocument();
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.preview' }));
    expect(onPreview).toHaveBeenCalledWith('builtin:default_minutes');
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.add_to_mine' }));
    expect(onAddToMine).toHaveBeenCalledWith(['builtin:default_minutes']);
    expect(within(row).queryByRole('button', { name: 'meetings.templates.edit' })).toBeNull();
    expect(within(row).queryByRole('button', { name: 'meetings.templates.delete' })).toBeNull();
  });

  it('a user row offers preview, edit, duplicate and delete', async () => {
    const { user, onEdit, onDuplicate, onDelete } = render();
    const mine = section('meetings.templates.mine_title');
    await user.click(
      within(mine).getByRole('button', { name: /meetings\.templates\.category\.custom/ })
    );
    const row = within(mine).getByRole('listitem', { name: 'Retro' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.edit' }));
    expect(onEdit).toHaveBeenCalledWith('user:2');
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.duplicate' }));
    expect(onDuplicate).toHaveBeenCalledWith('user:2');
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.delete' }));
    expect(onDelete).toHaveBeenCalledWith(['user:2']);
  });

  it('flags a transcript template as long and paid like a whole meeting', async () => {
    const { user } = render();
    const builtins = section('meetings.templates.builtin_title');
    await user.click(
      within(builtins).getByRole('button', { name: /meetings\.templates\.category\.transcript/ })
    );
    const row = within(builtins).getByRole('listitem', { name: 'Clean transcript' });
    expect(within(row).getByText('meetings.templates.transcript_badge')).toBeInTheDocument();
  });
});

describe('MeetingTemplateLibrary — selection', () => {
  it('adds a selection of built-ins to my templates from the section bar', async () => {
    const { user, onAddToMine } = render();
    const builtins = section('meetings.templates.builtin_title');
    await user.click(
      within(builtins).getByRole('button', { name: /meetings\.templates\.category\.meeting/ })
    );
    await user.click(
      within(within(builtins).getByRole('listitem', { name: 'Meeting minutes' })).getByRole(
        'checkbox'
      )
    );
    await user.click(
      within(within(builtins).getByRole('listitem', { name: 'Daily standup' })).getByRole(
        'checkbox'
      )
    );
    const bar = within(builtins).getByRole('region', {
      name: 'meetings.templates.selection_region',
    });
    expect(within(bar).getByText('meetings.templates.selected_count')).toBeInTheDocument();
    await user.click(within(bar).getByRole('button', { name: 'meetings.templates.add_selected' }));
    expect(onAddToMine).toHaveBeenCalledWith(['builtin:default_minutes', 'builtin:daily_standup']);
  });

  it('deletes a selection of my templates from the section bar, and select-all covers every row', async () => {
    const { user, onDelete } = render();
    const mine = section('meetings.templates.mine_title');
    await user.click(
      within(mine).getByRole('button', { name: /meetings\.templates\.category\.custom/ })
    );
    await user.click(
      within(within(mine).getByRole('listitem', { name: 'Retro' })).getByRole('checkbox')
    );
    const bar = within(mine).getByRole('region', { name: 'meetings.templates.selection_region' });
    // Select-all reaches the rows of the folded categories too.
    await user.click(within(bar).getByRole('checkbox', { name: 'meetings.templates.select_all' }));
    await user.click(
      within(bar).getByRole('button', { name: 'meetings.templates.delete_selected' })
    );
    expect(onDelete).toHaveBeenCalledWith(['user:2', 'user:1']);
  });

  it('refuses to add built-ins beyond the cap and says so', async () => {
    const { user, onAddToMine } = render({ maxUserTemplates: 2 });
    const builtins = section('meetings.templates.builtin_title');
    await user.click(
      within(builtins).getByRole('button', { name: /meetings\.templates\.category\.meeting/ })
    );
    const row = within(builtins).getByRole('listitem', { name: 'Meeting minutes' });
    const add = within(row).getByRole('button', { name: 'meetings.templates.add_to_mine' });
    expect(add).toHaveAttribute('aria-disabled', 'true');
    await user.click(add);
    expect(onAddToMine).not.toHaveBeenCalled();
    expect(screen.getByText('meetings.templates.limit_reached')).toBeInTheDocument();
  });

  it('refuses a second add while a batch runs, and shows which row is being fetched', async () => {
    const { user, onAddToMine } = render({ busy: true, busyRef: 'builtin:default_minutes' });
    const builtins = section('meetings.templates.builtin_title');
    await user.click(
      within(builtins).getByRole('button', { name: /meetings\.templates\.category\.meeting/ })
    );
    const row = within(builtins).getByRole('listitem', { name: 'Meeting minutes' });
    await user.click(within(row).getByRole('button', { name: 'meetings.templates.add_to_mine' }));
    expect(onAddToMine).not.toHaveBeenCalled();
    // The fetched row's preview is stated busy (spinner + disabled), the others are not.
    expect(within(row).getByRole('button', { name: 'meetings.templates.preview' })).toBeDisabled();
    const other = within(builtins).getByRole('listitem', { name: 'Daily standup' });
    expect(within(other).getByRole('button', { name: 'meetings.templates.preview' })).toBeEnabled();
  });
});
