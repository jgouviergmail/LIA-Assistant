/** Complete-film selection, keyboard closure, media cleanup and failed-read recovery. */
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import type { LandingVideoDescriptor } from '@/lib/landing/media';
import PresentationDialog from '../PresentationDialog';

vi.unmock('react-i18next');

const FILM: LandingVideoDescriptor = {
  poster: 'https://media.example.org/full.webp',
  renditions: [
    { src: 'https://media.example.org/full-hd.mp4', type: 'video/mp4', minWidth: 900 },
    { src: 'https://media.example.org/full-mobile.mp4', type: 'video/mp4' },
  ],
  aspectRatio: [16, 9],
  durationSeconds: 158,
  hasBeats: true,
  credit: null,
  aiGenerated: true,
};

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open presentation</button>
      {open && <PresentationDialog request={1} onClose={() => setOpen(false)} />}
    </>
  );
}

async function mount(language: 'en' | 'fr' = 'fr') {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  render(
    <I18nextProvider i18n={i18n}>
      <Harness />
    </I18nextProvider>
  );
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Open presentation' }));
  return user;
}

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => response({ presentation: FILM }))
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Complete presentation', () => {
  it.each(['en', 'fr'] as const)('has localized controls and disclosure in %s', async language => {
    await mount(language);
    const copy = language === 'fr' ? fr : en;
    const film = await screen.findByLabelText(copy.landing.presentation.film.title, {
      selector: 'video',
    });
    expect(film).toHaveAttribute('controls');
    expect(film).not.toHaveAttribute('loop');
    expect(film.querySelector('source')).toHaveAttribute('src', FILM.renditions[0].src);
    expect(screen.getByText(copy.landing.presentation.film.ai_music_note)).toBeVisible();
    expect(screen.getByRole('button', { name: copy.common.close })).toBeVisible();
  });

  it('closes with Escape, pauses the media and returns focus to the opener', async () => {
    const user = await mount();
    const film = await screen.findByLabelText(fr.landing.presentation.film.title, {
      selector: 'video',
    });
    const pause = vi.mocked(HTMLMediaElement.prototype.pause);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(pause.mock.contexts).toContain(film);
    expect(screen.getByRole('button', { name: 'Open presentation' })).toHaveFocus();
  });

  it('never substitutes a teaser or an unrelated playlist for a missing full film', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ video: FILM, next: [FILM] })));
    await mount();
    expect(await screen.findByText(fr.landing.presentation.film.unavailable)).toBeVisible();
    expect(document.querySelector('video')).toBeNull();
  });

  it('recovers from a failed metadata read on an explicit retry', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({}, 503))
      .mockResolvedValueOnce(response({ presentation: FILM }));
    vi.stubGlobal('fetch', fetchMock);
    const user = await mount();
    expect(await screen.findByText(fr.landing.presentation.film.error)).toBeVisible();
    await user.click(screen.getByRole('button', { name: fr.common.retry }));
    expect(
      await screen.findByLabelText(fr.landing.presentation.film.title, { selector: 'video' })
    ).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('offers recovery when the browser cannot decode the film', async () => {
    const user = await mount();
    const film = await screen.findByLabelText(fr.landing.presentation.film.title, {
      selector: 'video',
    });
    fireEvent.error(film);
    expect(await screen.findByText(fr.landing.presentation.film.error)).toBeVisible();
    await user.click(screen.getByRole('button', { name: fr.common.retry }));
    expect(
      await screen.findByLabelText(fr.landing.presentation.film.title, { selector: 'video' })
    ).toBeVisible();
  });

  it('aborts a pending metadata read when the viewer closes', async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, options: RequestInit) => {
        signal = options.signal ?? undefined;
        return new Promise<Response>(() => undefined);
      })
    );
    const user = await mount();
    await waitFor(() => expect(signal).toBeDefined());
    await user.keyboard('{Escape}');
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
