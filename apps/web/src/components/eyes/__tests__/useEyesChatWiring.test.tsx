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
    useEyesSignalsStore.getState().setReaction('joy', Date.now());
    const { rerender } = render(<Probe status="idle" messages={[]} />);
    rerender(<Probe status="sending" messages={[]} />);
    expect(useEyesSignalsStore.getState().lastStepKind).toBeNull();
    expect(useEyesSignalsStore.getState().reaction).toBeNull();
  });

  it('streaming → idle reacts from the per-turn psyche self-report', () => {
    const message = assistantMessage({
      metadata: {
        psyche_state: {
          mood_label: 'serene',
          active_emotions: [{ name: 'enthusiasm', intensity: 0.8 }],
        },
      },
    });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    expect(useEyesSignalsStore.getState().reaction?.expression).toBe('excited');
  });

  it('falls back to the content heuristic when the snapshot is missing', () => {
    const message = assistantMessage({ content: 'Souhaitez-vous que je continue ?' });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    expect(useEyesSignalsStore.getState().reaction?.expression).toBe('question');
  });

  it('stores no reaction for a plain informative answer', () => {
    const message = assistantMessage({ content: 'La réunion est à 15h.' });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    expect(useEyesSignalsStore.getState().reaction).toBeNull();
  });

  it('a generated artifact reads as joy even with plain text', () => {
    const message = assistantMessage({
      content: 'Voici le document.',
      generatedDocuments: [{ url: '/d/1', filename: 'doc.pdf', doc_type: 'pdf', size_bytes: 1024 }],
    });
    const { rerender } = render(<Probe status="streaming" messages={[message]} />);
    rerender(<Probe status="idle" messages={[message]} />);
    expect(useEyesSignalsStore.getState().reaction?.expression).toBe('joy');
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
