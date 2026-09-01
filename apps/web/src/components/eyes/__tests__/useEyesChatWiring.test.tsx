/**
 * useEyesChatWiring — per-turn signal wiring contract.
 *
 * Drives the hook through real status transitions with a probe component and
 * asserts against the signals store: new-turn reset, post-completion reaction
 * (psyche self-report first, heuristic fallback, none on plain text), the
 * no-reaction guarantee on history hydration, and the two recorders.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render } from '@testing-library/react';

import { useEyesChatWiring } from '../useEyesChatWiring';
import { useEyesSignalsStore } from '@/stores/eyesSignalsStore';
import type { Message } from '@/types/chat';
import type { ChatState } from '@/types/chat-state';

function Probe({ status, messages }: { status: ChatState['status']; messages: Message[] }) {
  const wiring = useEyesChatWiring(status, messages);
  return (
    <button type="button" aria-label="probe" onClick={() => wiring.onTyping('hello')}>
      probe
    </button>
  );
}

function assistantMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'a1',
    role: 'assistant',
    content: 'Réponse.',
    timestamp: new Date(),
    ...overrides,
  };
}

beforeEach(() => {
  useEyesSignalsStore.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useEyesChatWiring', () => {
  it('idle → sending starts a new turn (clears step kind and reaction)', () => {
    useEyesSignalsStore.getState().recordStep('tool');
    useEyesSignalsStore.getState().setReaction('joy', 1, 'none', Date.now());
    const { rerender } = render(<Probe status="idle" messages={[]} />);
    rerender(<Probe status="sending" messages={[]} />);
    expect(useEyesSignalsStore.getState().lastStepKind).toBeNull();
    expect(useEyesSignalsStore.getState().reaction).toBeNull();
  });

  it('streaming → idle reacts from the REGISTER the answer declared', () => {
    useEyesSignalsStore
      .getState()
      .setTone({ register: 'celebratory', intensity: 0.9, accent: 'sparkle' });
    const message = assistantMessage({ content: 'Termine.' });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    const reaction = useEyesSignalsStore.getState().reaction;
    expect(reaction?.expression).toBe('excited');
    expect(reaction?.accent).toBe('sparkle');
    // A celebration is played BIG — that is the whole point of a declared
    // intensity the renderer is allowed to overplay.
    expect(reaction?.emphasis).toBeGreaterThan(1.4);
  });

  it('IGNORES a psyche self-report, however strong', () => {
    // The defect this closed: over fourteen consecutive production turns the
    // psyche named `enthusiasm` on thirteen of them, drifting by 0.02, so the
    // face was identical every time. A trait cannot answer for one turn.
    const message = assistantMessage({
      content: 'Voici la liste des taches du jour.',
      metadata: {
        psyche_state: {
          mood_label: 'serene',
          active_emotions: [{ name: 'enthusiasm', intensity: 0.95 }],
        },
      },
    });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    // The answer's SHAPE decides instead, and a plain informative one is
    // `factual` — the resting face, played with intent. What matters is that
    // a 0.95 `enthusiasm` bought nothing.
    expect(useEyesSignalsStore.getState().reaction?.expression).toBe('neutral');
  });

  it('a plain answer earns an HONEST face, not a grin and not nothing', () => {
    // Measured on 16 consecutive real turns: the declared tag arrives on a
    // minority of them, so "no tag, no reaction" would leave the face inert
    // most of the time. A plain answer is `factual`, played small.
    const message = assistantMessage({ content: 'Le rendez-vous est a 14h.' });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    const reaction = useEyesSignalsStore.getState().reaction;
    expect(reaction?.expression).toBe('neutral');
    expect(reaction?.emphasis).toBeLessThan(1.1);
  });

  it('falls back to the content heuristic when the snapshot is missing', () => {
    const message = assistantMessage({ content: 'Souhaitez-vous que je continue ?' });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    expect(useEyesSignalsStore.getState().reaction?.expression).toBe('question');
  });

  it('plays a technical delivery as ASSURED, never as a celebration', () => {
    // The complaint that started this: every answer ended on the same smile.
    const message = assistantMessage({ content: 'Voici :\n```sh\ntask lint\n```' });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    expect(useEyesSignalsStore.getState().reaction?.expression).toBe('focused');
  });

  it('a generated artifact is a small event, and it sparkles', () => {
    const message = assistantMessage({
      content: 'Voici le document.',
      generatedDocuments: [{ url: '/d/1', filename: 'doc.pdf', doc_type: 'pdf', size_bytes: 1024 }],
    });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    const reaction = useEyesSignalsStore.getState().reaction;
    expect(reaction?.expression).toBe('excited');
    expect(reaction?.accent).toBe('sparkle');
  });

  it('history hydration (idle → idle with new messages) never reacts', () => {
    const { rerender } = render(<Probe status="idle" messages={[]} />);
    rerender(<Probe status="idle" messages={[assistantMessage({ content: 'Une question ?' })]} />);
    expect(useEyesSignalsStore.getState().reaction).toBeNull();
  });

  it('returns a render-stable object (page callbacks fold it into their deps)', () => {
    const seen: unknown[] = [];
    function IdentityProbe({ status }: { status: ChatState['status'] }) {
      seen.push(useEyesChatWiring(status, []));
      return null;
    }
    const { rerender } = render(<IdentityProbe status="idle" />);
    rerender(<IdentityProbe status="idle" />);
    expect(seen).toHaveLength(2);
    expect(seen[0]).toBe(seen[1]);
  });

  it('onTyping records only non-empty input; onNotification records a ping', () => {
    vi.setSystemTime?.(new Date());
    function Recorders() {
      const wiring = useEyesChatWiring('idle', []);
      return (
        <>
          <button
            type="button"
            aria-label="empty"
            onClick={() => wiring.onTyping('')}
            data-testid="empty"
          />
          <button
            type="button"
            aria-label="typed"
            onClick={() => wiring.onTyping('a')}
            data-testid="typed"
          />
          <button
            type="button"
            aria-label="notif"
            onClick={() => wiring.onNotification()}
            data-testid="notif"
          />
        </>
      );
    }
    const { getByTestId } = render(<Recorders />);
    getByTestId('empty').click();
    expect(useEyesSignalsStore.getState().typingAt).toBeNull();
    getByTestId('typed').click();
    expect(useEyesSignalsStore.getState().typingAt).not.toBeNull();
    getByTestId('notif').click();
    expect(useEyesSignalsStore.getState().notificationAt).not.toBeNull();
  });
});
