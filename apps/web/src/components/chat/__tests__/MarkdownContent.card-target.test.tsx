/** Item links revalidate their signed source before opening a native tool. */
import { act, fireEvent, render as renderRaw, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { MarkdownContent } from '../MarkdownContent';
import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import { CardToolsAvailable, cardToolsConfig } from './card-target-fixtures';
const render = (ui: ReactElement) => renderRaw(ui, { wrapper: CardToolsAvailable });

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push }),
  usePathname: () => '/fr/dashboard/chat',
}));

const target = {
  kind: 'email',
  item_id: 'mail/with & punctuation',
  container_id: 'Inbox & archive',
  day: null,
  is_folder: false,
};

function card(token: string | null = 'signed-token'): string {
  return `<div class="lia-card-binding" data-card-kind="email" ${token ? `data-card-target="${token}"` : ''}>
  <div class="lia-card lia-email"><a class="lia-email__subject" href="https://mail.google.com/mail/u/0/#inbox/old" target="_blank">A real subject</a>
  <a href="https://maps.google.com/?q=office">Office map</a><a href="mailto:person@example.org">Write</a></div></div>`;
}

beforeEach(() => nav.push.mockClear());
afterEach(() => vi.restoreAllMocks());

describe('card item navigation', () => {
  it.each([null, cardToolsConfig(false)])(
    'keeps facts but offers no withdrawn or unknown capability',
    config => {
      const post = vi.spyOn(apiClient, 'post');
      renderRaw(
        <AppConfigSeedContext.Provider value={config}>
          <MarkdownContent content={card()} />
        </AppConfigSeedContext.Provider>
      );
      expect(screen.getByText('A real subject')).toBeVisible();
      expect(
        screen.queryByRole('button', { name: /A real subject|card_tools.open/ })
      ).not.toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'A real subject' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByText('A real subject'));
      expect(post).not.toHaveBeenCalled();
      expect(nav.push).not.toHaveBeenCalled();
    }
  );

  it('cancels a pending open when the shared capability is withdrawn', async () => {
    const pending = Promise.withResolvers<unknown>();
    const post = vi.spyOn(apiClient, 'post').mockImplementation(() => pending.promise);
    const page = (offered: boolean) => (
      <AppConfigSeedContext.Provider value={cardToolsConfig(offered)}>
        <MarkdownContent content={card()} />
      </AppConfigSeedContext.Provider>
    );
    const view = renderRaw(page(true));
    fireEvent.click(screen.getByRole('button', { name: 'A real subject' }));
    view.rerender(page(false));
    expect(post.mock.calls[0][2]?.signal?.aborted).toBe(true);
    await act(async () => pending.resolve({ available: true, target, reason: null }));
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'card_tools.open_tool' })).not.toBeInTheDocument();
  });

  it('reactivates idle and ignores the former answer while a new check is pending', async () => {
    const first = Promise.withResolvers<unknown>();
    const second = Promise.withResolvers<unknown>();
    const post = vi
      .spyOn(apiClient, 'post')
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const page = (offered: boolean) => (
      <AppConfigSeedContext.Provider value={cardToolsConfig(offered)}>
        <MarkdownContent content={card()} />
      </AppConfigSeedContext.Provider>
    );
    const view = renderRaw(page(true));
    fireEvent.click(screen.getByRole('button', { name: 'A real subject' }));
    view.rerender(page(false));
    view.rerender(page(true));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    const title = screen.getByRole('button', { name: 'A real subject' });
    expect(title).toHaveAttribute('aria-disabled', 'false');
    fireEvent.click(title);
    await act(async () => first.resolve({ available: true, target, reason: null }));
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.opening');
    expect(post).toHaveBeenCalledTimes(2);
    await act(async () => second.resolve({ available: true, target, reason: null }));
    expect(nav.push).toHaveBeenCalledOnce();
  });
  it('keeps the source inert until keyboard activation and opens the verified item', async () => {
    const post = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValue({ available: true, target, reason: null });
    const user = userEvent.setup();
    render(<MarkdownContent content={card()} />);
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: 'A real subject' })).not.toBeInTheDocument();
    const title = screen.getByRole('button', { name: 'A real subject' });
    title.focus();
    await user.keyboard('{Enter}');
    await waitFor(() => expect(nav.push).toHaveBeenCalledOnce());
    expect(post).toHaveBeenCalledWith(
      '/workbench/card-target',
      { token: 'signed-token' },
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    const destination = new URL(nav.push.mock.calls[0][0], 'https://lia.test');
    expect(destination.pathname).toBe('/dashboard/tools/mail');
    expect(Object.fromEntries(destination.searchParams)).toEqual({
      id: target.item_id,
      folder: target.container_id,
      card_source: 'signed-token',
    });
    expect(screen.getByRole('link', { name: 'Office map' })).toHaveAttribute(
      'href',
      'https://maps.google.com/?q=office'
    );
    expect(screen.getByRole('link', { name: 'Write' })).toHaveAttribute(
      'href',
      'mailto:person@example.org'
    );
  });

  it.each(['source_changed', 'unavailable'] as const)(
    'says %s and never navigates to the old provider',
    async reason => {
      vi.spyOn(apiClient, 'post').mockResolvedValue({ available: false, target: null, reason });
      render(<MarkdownContent content={card()} />);
      fireEvent.click(screen.getByRole('button', { name: 'A real subject' }));
      expect(await screen.findByRole('status')).toHaveTextContent(`card_tools.${reason}`);
      expect(nav.push).not.toHaveBeenCalled();
    }
  );

  it('explains a historical card without a request and offers only the unscoped tool', async () => {
    const post = vi.spyOn(apiClient, 'post');
    render(<MarkdownContent content={card(null)} />);
    fireEvent.click(screen.getByRole('button', { name: 'A real subject' }));
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.historical');
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'card_tools.open_tool' }));
    expect(nav.push).toHaveBeenCalledWith('/dashboard/tools/mail');
  });

  it('keeps focus on network failure and retries the same verified door', async () => {
    const post = vi
      .spyOn(apiClient, 'post')
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ available: true, target, reason: null });
    render(<MarkdownContent content={card()} />);
    const title = screen.getByRole('button', { name: 'A real subject' });
    title.focus();
    fireEvent.click(title);
    expect(await screen.findByRole('status')).toHaveTextContent('card_tools.error');
    expect(title).toHaveFocus();
    expect(nav.push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'card_tools.retry' }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledOnce());
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('rejects a malformed target instead of guessing an address', async () => {
    vi.spyOn(apiClient, 'post').mockResolvedValue({
      available: true,
      target: { ...target, kind: 'unknown' },
      reason: null,
    });
    render(<MarkdownContent content={card()} />);
    fireEvent.click(screen.getByRole('button', { name: 'A real subject' }));
    expect(await screen.findByRole('status')).toHaveTextContent('card_tools.unavailable');
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('aborts its read on unmount and never follows a late answer', async () => {
    let answer: (value: unknown) => void = () => undefined;
    const post = vi.spyOn(apiClient, 'post').mockImplementation(
      () =>
        new Promise(resolve => {
          answer = resolve;
        })
    );
    const view = render(<MarkdownContent content={card()} />);
    fireEvent.click(screen.getByRole('button', { name: 'A real subject' }));
    view.unmount();
    expect(post.mock.calls[0][2]?.signal?.aborted).toBe(true);
    await act(async () => answer({ available: true, target, reason: null }));
    expect(nav.push).not.toHaveBeenCalled();
  });

  it('recognizes old unbound cards without treating their provider href as authority', () => {
    const post = vi.spyOn(apiClient, 'post');
    render(
      <MarkdownContent
        content={
          '<div class="lia-card lia-contact"><a class="lia-card-top__title" href="https://contacts.google.com/person/old">Old contact</a><a class="lia-action-btn" href="https://contacts.google.com/person/old">Provider action</a></div>'
        }
      />
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Old contact' }));
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.historical');
    fireEvent.click(screen.getByRole('button', { name: 'card_tools.open_tool' }));
    expect(post).not.toHaveBeenCalled();
    expect(nav.push).toHaveBeenCalledWith('/dashboard/tools/contacts');
  });

  it('keeps historical source actions outside the card inside the same native boundary', () => {
    render(
      <MarkdownContent
        content={
          '<div class="lia-response-wrapper"><div class="lia-card lia-contact"><a class="lia-card-top__title" href="https://contacts.google.com/person/old">Old contact</a></div><div class="lia-actions"><a class="lia-action-btn" href="https://contacts.google.com/person/old"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">open_in_new</span></span>Provider action</a><a href="https://meet.google.com/other">Join meeting</a></div></div>'
        }
      />
    );
    expect(screen.queryByRole('link', { name: /Provider action/ })).not.toBeInTheDocument();
    const action = screen.getByRole('button', { name: 'card_tools.open_item' });
    expect(action.querySelector('.lia-action-btn__icon svg')).toHaveAttribute(
      'data-icon-name',
      'ExternalLink'
    );
    expect(action.querySelector('.lia-action-btn__icon')).toHaveAttribute('aria-hidden', 'true');
    fireEvent.click(action);
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.historical');
    expect(screen.getByRole('link', { name: 'Join meeting' })).toHaveAttribute(
      'href',
      'https://meet.google.com/other'
    );
  });

  it.each(['lia-calendar', 'lia-hues'])('offers an explicit historical open for %s', family => {
    render(
      <MarkdownContent
        content={`<div class="lia-card ${family}"><span class="lia-card-top__title">Snapshot</span></div>`}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'card_tools.open_item' }));
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.historical');
  });

  it('does not mistake the email sender for an existing source opener', () => {
    render(
      <MarkdownContent
        content={
          '<div class="lia-card lia-email"><a class="lia-card-top__title" href="mailto:sender@example.test">Sender</a><span class="lia-email__subject">Subject without provider URL</span></div>'
        }
      />
    );
    expect(screen.getByRole('link', { name: 'Sender' })).toHaveAttribute(
      'href',
      'mailto:sender@example.test'
    );
    fireEvent.click(screen.getByRole('button', { name: 'card_tools.open_item' }));
    expect(screen.getByRole('status')).toHaveTextContent('card_tools.historical');
  });

  it('converts the source thumbnail and marked action while retaining attachment links', () => {
    render(
      <MarkdownContent
        content={
          '<div class="lia-card-binding" data-card-kind="file" data-card-target="file-token"><div class="lia-card lia-file"><a class="lia-card-top__title" href="https://drive.google.com/file/old">Project</a><a class="lia-file__preview" href="https://drive.google.com/file/old"><span>Thumbnail</span></a><a class="lia-action-btn" data-card-open="true" href="https://provider.test/alternate">Provider</a><a href="https://provider.test/attachment">Attachment</a></div></div>'
        }
      />
    );
    const controls = screen.getAllByRole('button', { name: 'card_tools.open_item' });
    expect(controls).toHaveLength(2);
    for (const control of controls) expect(control).not.toHaveAttribute('href');
    expect(controls[0]).toHaveTextContent('Thumbnail');
    expect(screen.getByRole('link', { name: 'Attachment' })).toHaveAttribute(
      'href',
      'https://provider.test/attachment'
    );
  });

  it('coalesces rapid activations and ignores an answer for a replaced card token', async () => {
    let answer: (value: unknown) => void = () => undefined;
    const post = vi.spyOn(apiClient, 'post').mockImplementation(
      () =>
        new Promise(resolve => {
          answer = resolve;
        })
    );
    const view = render(<MarkdownContent content={card()} />);
    const title = screen.getByRole('button', { name: 'A real subject' });
    fireEvent.click(title);
    fireEvent.click(title);
    expect(post).toHaveBeenCalledOnce();
    expect(title).toHaveAttribute('aria-disabled', 'true');
    view.rerender(<MarkdownContent content={card('replacement')} />);
    expect(post.mock.calls[0][2]?.signal?.aborted).toBe(true);
    await act(async () => answer({ available: true, target, reason: null }));
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
