import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const { open, config } = vi.hoisted(() => ({
  open: vi.fn(),
  config: { features: { attachments_enabled: true } },
}));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: open }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig: () => ({ config }) }));

import { parseAttachSource } from '@/lib/attach-source-link';
import { UseInChatButton } from '../UseInChatButton';

const ID = '11111111-2222-4333-8444-555555555555';

describe('UseInChatButton', () => {
  it('opens the chat on a link naming the source — the composer makes the copy', () => {
    render(<UseInChatButton lng="fr" source={{ kind: 'generated', id: ID }} label="Use it" />);

    fireEvent.click(screen.getByRole('button', { name: 'Use it' }));

    const href = new URL(open.mock.calls[0][0], 'http://localhost');
    expect(href.pathname).toBe('/fr/dashboard/chat');
    expect([...href.searchParams.keys()]).toEqual(['attach']);
    expect(parseAttachSource(href.searchParams.get('attach'))).toEqual({
      kind: 'generated',
      id: ID,
    });
  });

  it('is not drawn where the instance takes no attachment', () => {
    config.features.attachments_enabled = false;
    render(<UseInChatButton lng="fr" source={{ kind: 'bookmark', id: ID }} label="Use it" />);
    expect(screen.queryByRole('button', { name: 'Use it' })).not.toBeInTheDocument();
    config.features.attachments_enabled = true;
  });
});
