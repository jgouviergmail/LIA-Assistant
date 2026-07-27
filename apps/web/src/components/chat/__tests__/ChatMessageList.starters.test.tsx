/**
 * Empty-chat starters (W8).
 *
 * The empty chat used to be a greeting and nothing else — the one screen where
 * a newcomer has the least idea what to type. What must hold:
 *
 *  1. the starters exist, are real buttons, and hand back the phrase the user
 *     read — never a key, never a truncated label;
 *  2. they PREFILL and never send (they share the follow-up chips' rail, which
 *     the page owns; here we assert the callback contract);
 *  3. they vanish the moment the conversation has content — a chat with
 *     messages must not carry beginner scaffolding;
 *  4. without a handler nothing clickable is rendered, so no dead control.
 */

import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { Message } from '@/types/chat';

// Declared inside `vi.hoisted` (it runs before the module mocks) and reused by
// the assertions, so the expected wording exists in exactly one place.
const { CONTENT, translate } = vi.hoisted(() => {
  const content: Record<string, string> = {
    'chat.starters.label': 'Essayez par exemple',
    'chat.starters.capabilities': 'Que sais-tu faire ?',
    'chat.starters.reminder': "Rappelle-moi d'appeler Jean vendredi à 18h",
    'chat.starters.explain': "Explique-moi l'informatique quantique simplement",
    'chat.empty_state.title': 'Commencez une conversation',
    'chat.empty_state.description': 'Posez votre question',
  };
  return {
    CONTENT: content,
    translate: (key: string, params?: Record<string, unknown>) => {
      const value = key in content ? content[key] : key;
      return params
        ? value.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(params[name] ?? ''))
        : value;
    },
  };
});

vi.mock('react-i18next', async importOriginal => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: translate,
      i18n: { language: 'fr', changeLanguage: vi.fn() },
    }),
  };
});

// Rendering a real message mounts ChatMessage, which reads the auth context
// and issues feedback mutations. Same stubs as ChatMessageList.test.tsx.
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { tokens_display_enabled: false } }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: vi.fn() }) }));

import { ChatMessageList } from '../ChatMessageList';

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'Bonjour',
    timestamp: new Date('2026-07-26T08:00:00Z'),
    ...overrides,
  } as Message;
}

describe('empty-chat starters', () => {
  it('offers a way in when the conversation is empty', () => {
    renderWithProviders(<ChatMessageList messages={[]} onStarterPick={vi.fn()} />);

    expect(screen.getByRole('group', { name: 'Essayez par exemple' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: CONTENT['chat.starters.capabilities'] })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: CONTENT['chat.starters.reminder'] })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: CONTENT['chat.starters.explain'] })
    ).toBeInTheDocument();
  });

  it('hands back the exact phrase the user read', async () => {
    const onStarterPick = vi.fn();
    renderWithProviders(<ChatMessageList messages={[]} onStarterPick={onStarterPick} />);

    await userEvent.click(screen.getByRole('button', { name: CONTENT['chat.starters.reminder'] }));

    expect(onStarterPick).toHaveBeenCalledWith("Rappelle-moi d'appeler Jean vendredi à 18h");
    expect(onStarterPick).toHaveBeenCalledTimes(1);
  });

  it('never resolves a translation key as a starter', () => {
    // A missing key would render "chat.starters.explain" as a clickable phrase
    // and send that to the model.
    renderWithProviders(<ChatMessageList messages={[]} onStarterPick={vi.fn()} />);
    const group = screen.getByRole('group', { name: 'Essayez par exemple' });
    expect(group.textContent).not.toContain('chat.starters');
  });

  it('disappears as soon as the conversation has content', () => {
    // Beginner scaffolding must not survive into a real conversation.
    renderWithProviders(<ChatMessageList messages={[message()]} onStarterPick={vi.fn()} />);
    expect(screen.queryByRole('group', { name: 'Essayez par exemple' })).not.toBeInTheDocument();
  });

  it('renders nothing clickable without a handler', () => {
    renderWithProviders(<ChatMessageList messages={[]} />);
    expect(screen.queryByRole('group', { name: 'Essayez par exemple' })).not.toBeInTheDocument();
    // The greeting itself is untouched.
    expect(screen.getByText('Commencez une conversation')).toBeInTheDocument();
  });

  it('keeps the buttons out of any form submission path', () => {
    renderWithProviders(<ChatMessageList messages={[]} onStarterPick={vi.fn()} />);
    for (const button of screen.getAllByRole('button')) {
      expect(button).toHaveAttribute('type', 'button');
    }
  });
});
