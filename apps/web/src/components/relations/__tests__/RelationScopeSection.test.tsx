/**
 * The 360° scope selector — a selection, not a suggestion.
 *
 * The request leaves this page as a chat `?intent=` carrying prose only, so
 * what the reader ticks has to be SAVED before the chat opens. The oracles
 * here are about that guarantee and its edges:
 *
 * - every source, direction and role is offered, pre-ticked from the stored
 *   scope, and each box is a real labelled checkbox (keyboard, screen reader);
 * - an empty selection is refused rather than silently turned into
 *   "everything" — a scope that grew when the reader cleared it would spend
 *   provider quota they just asked to save;
 * - the max-items field never leaves the bounds the server enforces, and a
 *   cleared field never becomes zero (which would fail the whole write and
 *   lose every box just ticked).
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { RelationOverviewScope } from '@/hooks/useRelations';

import { RelationScopeSection } from '../RelationScopeSection';

function scope(over: Partial<RelationOverviewScope> = {}): RelationOverviewScope {
  return {
    sections: [
      'contact',
      'open_loops',
      'calls',
      'memories',
      'peer_messages',
      'emails',
      'events',
    ],
    directions: ['received', 'sent'],
    roles: ['attendee', 'organizer'],
    max_items: 5,
    ...over,
  };
}

/** Renders the section and OPENS it — like every other, it starts folded. */
async function renderScope(over: Partial<RelationOverviewScope> = {}, props = {}) {
  const onChange = vi.fn();
  const onPrepare = vi.fn();
  const utils = renderWithProviders(
    <RelationScopeSection
      scope={scope(over)}
      saving={false}
      onChange={onChange}
      onPrepare={onPrepare}
      {...props}
    />
  );
  await utils.user.click(screen.getByRole('button', { name: /relations.scope_title/ }));
  return { ...utils, onChange, onPrepare };
}

describe('RelationScopeSection', () => {
  it('offers every source, direction and role, pre-ticked', async () => {
    await renderScope();
    const boxes = screen.getAllByRole('checkbox');
    // 7 sources + 2 directions + 2 roles.
    expect(boxes).toHaveLength(11);
    expect(boxes.every(box => (box as HTMLInputElement).checked)).toBe(true);
  });

  it('pre-fills from the STORED scope, not from "everything"', async () => {
    await renderScope({ sections: ['contact', 'emails'], roles: ['organizer'] });
    expect(screen.getByRole('checkbox', { name: 'relations.section_contact' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'relations.section_calls' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'relations.event_role_attendee' })).not.toBeChecked();
  });

  it('reports an unticked source without touching the rest', async () => {
    const { user, onChange } = await renderScope();
    await user.click(screen.getByRole('checkbox', { name: 'relations.section_calls' }));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0] as RelationOverviewScope;
    expect(next.sections).not.toContain('calls');
    expect(next.sections).toContain('contact');
    expect(next.directions).toEqual(['received', 'sent']);
    expect(next.max_items).toBe(5);
  });

  it('separates emission from reception, and attendee from organizer', async () => {
    const { user, onChange } = await renderScope();
    await user.click(screen.getByRole('checkbox', { name: 'relations.peer_message_sent' }));
    expect((onChange.mock.calls[0][0] as RelationOverviewScope).directions).toEqual(['received']);

    onChange.mockClear();
    await user.click(screen.getByRole('checkbox', { name: 'relations.event_role_organizer' }));
    expect((onChange.mock.calls[0][0] as RelationOverviewScope).roles).toEqual(['attendee']);
  });

  it('keeps the item count inside the bounds the server enforces', async () => {
    const { user, onChange } = await renderScope();
    const input = screen.getByRole('spinbutton', { name: /relations.scope_max_items/ });
    await user.clear(input);
    await user.type(input, '99');
    const last = onChange.mock.calls.at(-1)?.[0] as RelationOverviewScope;
    expect(last.max_items).toBeLessThanOrEqual(25);
  });

  it('never turns a cleared count into zero', async () => {
    // Zero fails the write server-side, and a rejected write loses every box
    // the reader just ticked.
    const { user, onChange } = await renderScope();
    await user.clear(screen.getByRole('spinbutton', { name: /relations.scope_max_items/ }));
    for (const call of onChange.mock.calls) {
      expect((call[0] as RelationOverviewScope).max_items).toBeGreaterThanOrEqual(1);
    }
  });

  it('refuses to run with nothing selected, and says why', async () => {
    const { user, onPrepare } = await renderScope({ sections: [] });
    expect(screen.getByText('relations.scope_empty')).toBeInTheDocument();
    const launch = screen.getByRole('button', { name: /relations.scope_launch/ });
    expect(launch).toHaveAttribute('aria-disabled', 'true');
    // `aria-disabled` keeps the control focusable, so the HANDLER is what
    // stops the action — the attribute alone would announce a refusal the
    // component does not honour.
    await user.click(launch);
    expect(onPrepare).not.toHaveBeenCalled();
  });

  it('refuses a second run while the first save is in flight', async () => {
    const { user, onPrepare } = await renderScope({}, { saving: true });
    await user.click(screen.getByRole('button', { name: /relations.scope_launch/ }));
    expect(onPrepare).not.toHaveBeenCalled();
  });

  it('hands the run over to the parent, which saves before navigating', async () => {
    const { user, onPrepare } = await renderScope();
    await user.click(screen.getByRole('button', { name: /relations.scope_launch/ }));
    expect(onPrepare).toHaveBeenCalledTimes(1);
  });

  it('stays reachable by keyboard while a save is in flight', async () => {
    await renderScope({}, { saving: true });
    const launch = screen.getByRole('button', { name: /relations.scope_launch/ });
    expect(launch).toHaveAttribute('aria-disabled', 'true');
    // NOT `disabled`: the browser blurs a focused control the moment it is
    // disabled, dropping the keyboard reader back onto <body>.
    expect(launch).not.toBeDisabled();
  });

  it('starts folded, like every other section of the panel', () => {
    renderWithProviders(
      <RelationScopeSection
        scope={scope()}
        saving={false}
        onChange={vi.fn()}
        onPrepare={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /relations.scope_title/ })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });
});
