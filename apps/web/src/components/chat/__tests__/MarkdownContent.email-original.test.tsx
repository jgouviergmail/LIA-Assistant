/**
 * A received message in the chat opens as the Tools show it (owner, 2026-11-14).
 *
 * The card's text stays; once its details are seen, the original layout is read under the card's
 * own signed source and drawn in the Tools' isolated frame, the text a click away. Nothing is read
 * for a card with no source proof, or with the Tools switched off; a layout that could not be read
 * is said, and the text stays.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import apiClient from '@/lib/api-client';
import { CARD_SOURCE_HEADER } from '@/lib/workbench/card-source';
import { MarkdownContent } from '../MarkdownContent';
import { cardToolsConfig } from './card-target-fixtures';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/fr/dashboard/chat',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'owner', timezone: 'Europe/Paris' } }),
}));

const HTML_PATH = '/workbench/mail/message/html';
const IMAGES_PATH = '/workbench/mail/message/images';
const FRAME = 'workbench.mail.html_frame_title';

/** An IntersectionObserver the test drives: nothing is seen until it says so. */
const watched: { callback: IntersectionObserverCallback; target: Element | null }[] = [];
class DrivenObserver {
  constructor(readonly callback: IntersectionObserverCallback) {
    watched.push({ callback, target: null });
  }
  observe(target: Element): void {
    watched[watched.length - 1].target = target;
  }
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

function seeDetails(): void {
  act(() => {
    for (const { callback, target } of watched) {
      if (!target) continue;
      callback(
        [{ isIntersecting: true, target } as IntersectionObserverEntry],
        {} as IntersectionObserver
      );
    }
  });
}

function card(token: string | null = 'signed-token'): string {
  return `<div class="lia-card-binding" data-card-kind="email" ${
    token ? `data-card-target="${token}"` : ''
  }><div class="lia-card lia-email"><a class="lia-email__subject" href="https://mail.google.com/mail/u/0/#all/m-1">Board meeting</a>
<details class="lia-collapsible" open><summary class="lia-collapsible__trigger">More</summary>
<div class="lia-email-original" data-message-id="m-1"><p>The message as text.</p></div>
</details></div></div>`;
}

function show(content: string, offered = true) {
  return render(
    <AppConfigSeedContext.Provider value={cardToolsConfig(offered)}>
      <MarkdownContent content={content} />
    </AppConfigSeedContext.Provider>
  );
}

/** The client's reads, typed as the client takes them. */
const spyOnGet = () => vi.spyOn(apiClient, 'get');
type GetSpy = ReturnType<typeof spyOnGet>;

function answer(html: string | null): GetSpy {
  return spyOnGet().mockImplementation(async (path: string) => {
    if (path === HTML_PATH) return { html, truncated: false };
    if (path === IMAGES_PATH) return { images: [], skipped: 0 };
    throw new Error(`unexpected read ${path}`);
  });
}

function htmlReads(get: GetSpy) {
  return get.mock.calls.filter(([path]) => path === HTML_PATH);
}

beforeEach(() => {
  watched.length = 0;
  vi.stubGlobal('IntersectionObserver', DrivenObserver);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('a mail card in the chat', () => {
  it('reads the original layout under the card source once seen, the text a click away', async () => {
    const get = answer('<h1>Board meeting</h1><p>Thursday 14:00</p>');
    const user = userEvent.setup();
    show(card());

    expect(htmlReads(get)).toHaveLength(0);
    expect(screen.getByText('The message as text.')).toBeInTheDocument();

    seeDetails();

    expect(await screen.findByTitle(FRAME)).toBeInTheDocument();
    const [, config] = htmlReads(get)[0];
    expect(config).toMatchObject({
      params: { id: 'm-1' },
      headers: { [CARD_SOURCE_HEADER]: 'signed-token' },
    });
    expect(screen.queryByText('The message as text.')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'workbench.mail.show_text' }));
    expect(screen.getByText('The message as text.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'workbench.mail.show_original' }));
    expect(await screen.findByTitle(FRAME)).toBeInTheDocument();
  });

  it('keeps the text, and offers nothing more, for a message with no layout', async () => {
    const get = answer(null);
    show(card());

    seeDetails();

    await waitFor(() => expect(htmlReads(get)).toHaveLength(1));
    expect(screen.getByText('The message as text.')).toBeInTheDocument();
    expect(screen.queryByTitle(FRAME)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'workbench.mail.show_original' })).toBeNull();
    expect(screen.queryByText('workbench.mail.html_failed')).toBeNull();
  });

  it('says a layout that could not be read, and keeps the text', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('source changed'));
    show(card());

    seeDetails();

    expect(await screen.findByText('workbench.mail.html_failed')).toBeInTheDocument();
    expect(screen.getByText('The message as text.')).toBeInTheDocument();
    expect(screen.queryByTitle(FRAME)).not.toBeInTheDocument();
  });

  it.each([
    { name: 'a card with no source proof', content: card(null), offered: true },
    { name: 'the Tools switched off', content: card(), offered: false },
  ])('reads nothing for $name', async ({ content, offered }) => {
    const get = answer('<p>layout</p>');
    show(content, offered);

    seeDetails();

    await act(async () => {});
    expect(get).not.toHaveBeenCalled();
    expect(screen.getByText('The message as text.')).toBeInTheDocument();
  });

  it('reads the images the layout carries under the same source', async () => {
    const get = answer('<p>Logo</p><img src="cid:logo@lia" alt="">');
    show(card());

    seeDetails();

    await screen.findByTitle(FRAME);
    await waitFor(() => expect(get.mock.calls.some(([path]) => path === IMAGES_PATH)).toBe(true));
    const [, config] = get.mock.calls.find(([path]) => path === IMAGES_PATH)!;
    expect(config).toMatchObject({
      params: { message_id: 'm-1', cid: ['logo@lia'] },
      headers: { [CARD_SOURCE_HEADER]: 'signed-token' },
    });
  });
});
