/**
 * The read-only preview (ADR-259): every section with its position, heading,
 * format and instruction, nothing editable, and « add to my templates » on a
 * built-in only — stated blocked at the cap yet still focusable.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { MeetingTemplate } from '@/types/meetings';

import { MeetingTemplatePreview } from '../MeetingTemplatePreview';

const TEMPLATE: MeetingTemplate = {
  ref: 'builtin:transcript_clean',
  id: null,
  name: 'Clean transcript',
  description: 'The exchange, cleaned.',
  category: 'transcript',
  sections: [
    {
      key: 'transcript',
      label: 'Transcript',
      instruction: 'Rewrite every turn.',
      kind: 'transcript',
    },
  ],
  builtin: true,
  builtin_key: null,
  auto_selectable: false,
};

describe('MeetingTemplatePreview', () => {
  it('shows the template, its badges and each section read-only', () => {
    renderWithProviders(<MeetingTemplatePreview lng="en" template={TEMPLATE} onBack={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Clean transcript' })).toBeInTheDocument();
    expect(screen.getByText('meetings.templates.category.transcript')).toBeInTheDocument();
    expect(screen.getByText('meetings.templates.builtin_badge')).toBeInTheDocument();
    expect(screen.getByText('meetings.templates.transcript_badge')).toBeInTheDocument();
    expect(screen.getByText('meetings.templates.sections_count')).toBeInTheDocument();
    expect(screen.getByText('Rewrite every turn.')).toBeInTheDocument();
    expect(screen.getByText('meetings.settings.kind_transcript')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    // Without a handler (one of my templates), nothing to add.
    expect(screen.queryByRole('button', { name: 'meetings.templates.add_to_mine' })).toBeNull();
  });

  it('goes back and adds to my templates, the add stated blocked at the cap yet still focusable', async () => {
    const onBack = vi.fn();
    const onAddToMine = vi.fn();
    const { user } = renderWithProviders(
      <MeetingTemplatePreview
        lng="en"
        template={TEMPLATE}
        onBack={onBack}
        onAddToMine={onAddToMine}
        addBlocked
      />
    );
    const add = screen.getByRole('button', { name: 'meetings.templates.add_to_mine' });
    expect(add).toHaveAttribute('aria-disabled', 'true');
    add.focus();
    expect(add).toHaveFocus();
    await user.click(add);
    expect(onAddToMine).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'meetings.templates.back_to_library' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
