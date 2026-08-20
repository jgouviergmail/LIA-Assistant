/**
 * FollowupChips (UXR Lot 4, A2) — tappable follow-up suggestions: real named
 * buttons, prefill-on-click (never a send), plain-text rendering (XSS
 * boundary), nothing rendered without suggestions.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { FollowupChips, visibleFollowups } from '../FollowupChips';
import { makeMessage } from '@/__tests__/factories';
import type { Message } from '@/types/chat';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const withChips = (over: Partial<Message> = {}): Message =>
  makeMessage({
    role: 'assistant',
    metadata: { followup_suggestions: ['Suite A', 'Suite B'] },
    ...over,
  });

describe('visibleFollowups — latest-only gate', () => {
  it('surfaces the latest assistant answer chips', () => {
    expect(visibleFollowups([makeMessage({ role: 'user' }), withChips()], false)).toEqual([
      'Suite A',
      'Suite B',
    ]);
  });

  it('disappears as soon as a newer turn starts (latest is the user)', () => {
    expect(visibleFollowups([withChips(), makeMessage({ role: 'user' })], false)).toEqual([]);
  });

  it('is empty while the surface is transiently busy (streaming / history view)', () => {
    // Competition with the usage wall and a pending approval moved to the
    // surface arbiter (S1, lib/chat-surfaces) — this flag is now only about
    // the surface being momentarily unusable.
    expect(visibleFollowups([withChips()], true)).toEqual([]);
  });

  it('tolerates absent or malformed metadata', () => {
    expect(visibleFollowups([makeMessage({ role: 'assistant' })], false)).toEqual([]);
    expect(
      visibleFollowups(
        [makeMessage({ role: 'assistant', metadata: { followup_suggestions: 'oops' } })],
        false
      )
    ).toEqual([]);
    expect(visibleFollowups([], false)).toEqual([]);
  });
});

describe('FollowupChips', () => {
  it('renders one real button per suggestion inside a named group', () => {
    render(
      <FollowupChips
        suggestions={['Montre la météo de demain', 'Ajoute un rappel']}
        onPick={vi.fn()}
      />
    );
    const group = screen.getByRole('group', { name: 'chat.followups.aria' });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Montre la météo de demain' })).toBeInTheDocument();
  });

  it('hands the exact text to onPick — a prefill, never a send', () => {
    const onPick = vi.fn();
    render(<FollowupChips suggestions={['Relance Alice sur le devis']} onPick={onPick} />);
    fireEvent.click(screen.getByRole('button', { name: 'Relance Alice sur le devis' }));
    expect(onPick).toHaveBeenCalledWith('Relance Alice sur le devis');
    expect(onPick).toHaveBeenCalledTimes(1);
  });

  it('renders suggestion text as plain children (XSS boundary)', () => {
    render(<FollowupChips suggestions={['<b>gras</b> & "quotes"']} onPick={vi.fn()} />);
    // The literal markup is TEXT, not parsed HTML.
    expect(screen.getByText('<b>gras</b> & "quotes"')).toBeInTheDocument();
    expect(document.querySelector('b')).toBeNull();
  });

  it('renders nothing at all without suggestions', () => {
    const { container } = render(<FollowupChips suggestions={[]} onPick={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});


describe('initiative motivation (Lot 1-A3)', () => {
  it('renders the provenance line above the chips', () => {
    render(
      <FollowupChips
        suggestions={['Cherche un plombier']}
        motivation="Parce que tu suis la Formule 1"
        onPick={() => {}}
      />
    );

    expect(screen.getByText('Parce que tu suis la Formule 1')).toBeInTheDocument();
  });

  it('renders nothing extra when the motivation is absent', () => {
    render(<FollowupChips suggestions={['Cherche un plombier']} onPick={() => {}} />);

    expect(screen.queryByText(/Parce que/)).not.toBeInTheDocument();
  });

  it('never shows a motivation without chips (page-level contract)', () => {
    const { container } = render(
      <FollowupChips suggestions={[]} motivation="orpheline" onPick={() => {}} />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
