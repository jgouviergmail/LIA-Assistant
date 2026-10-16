/** Native result notifications keep readable text, keyboard controls and the return route. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import postcss from 'postcss';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { toast } from 'sonner';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { meetingDetail } from '@/__tests__/fixtures/meeting-detail';
import { act, renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import { Toaster } from '@/components/ui/toaster';
import { useMeetingRecorder } from '@/hooks/useMeetingRecorder';
import { useMeetingRecorderStore } from '@/stores/meetingRecorderStore';
import type { Language } from '@/i18n/settings';
import type { MeetingDetail } from '@/types/meetings';

import { MeetingRecorderProvider } from '../MeetingRecorderProvider';

vi.unmock('react-i18next');
vi.mock('@/i18n/client', async () => {
  const { useTranslation } = await import('react-i18next');
  return { useTranslation: () => useTranslation() };
});

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ usePathname: () => '/fr/dashboard/settings' }));
vi.mock('@/hooks/useLocalizedRouter', () => ({ useLocalizedRouter: () => ({ push }) }));
// Stop at the recorder's completion boundary: browser capture/network belong to its own suite.
vi.mock('@/hooks/useMeetingRecorder', () => ({
  useMeetingRecorder: vi.fn(() => ({
    ...useMeetingRecorderStore.getState(),
    isSupported: true,
    isCapturing: false,
    isLive: false,
    start: vi.fn(async () => undefined),
    stop: vi.fn(async () => 'processing' as const),
    finalizeWithGaps: vi.fn(async () => 'processing' as const),
    resume: vi.fn(async () => undefined),
    discard: vi.fn(async () => undefined),
    dismiss: vi.fn(),
    continueAfterSilence: vi.fn(),
  })),
}));

const style = document.createElement('style');
beforeAll(() => {
  const css = postcss.parse(
    readFileSync(resolve(process.cwd(), 'src/styles/lia-overlays.css'), 'utf8')
  );
  // jsdom does not apply cascade layers. Flatten that wrapper only; exercise the real rules.
  css.walkAtRules('layer', layer => {
    if (layer.nodes) layer.replaceWith(...layer.nodes);
  });
  style.textContent = css.toString();
  document.head.append(style);
});
afterAll(() => style.remove());
afterEach(() => {
  act(() => toast.dismiss());
  vi.clearAllMocks();
});

async function mount(lng: Language) {
  const i18n = createInstance();
  await i18n.init({
    lng,
    fallbackLng: 'en',
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  return renderWithProviders(
    <I18nextProvider i18n={i18n}>
      <MeetingRecorderProvider lng={lng} enabled>
        <button type="button">Before the notification</button>
      </MeetingRecorderProvider>
      <Toaster duration={Infinity} />
    </I18nextProvider>
  );
}

function complete(detail: MeetingDetail) {
  const onProcessed = vi.mocked(useMeetingRecorder).mock.calls.at(-1)?.[0];
  if (!onProcessed) throw new Error('No recorder completion listener');
  act(() => onProcessed(detail));
}

const samples = [
  {
    lng: 'fr',
    close: 'Fermer',
    action: 'Ouvrir le compte rendu',
    ready: 'Compte rendu de réunion prêt',
    failed: "Le compte rendu n'a pas pu être produit",
    failure: "Le compte rendu n'a pas pu être rédigé.",
  },
  {
    lng: 'en',
    close: 'Close',
    action: 'Open the minutes',
    ready: 'Meeting minutes ready',
    failed: 'The minutes could not be produced',
    failure: 'The minutes could not be written.',
  },
] as const;

for (const sample of samples) {
  describe(`meeting result notification (${sample.lng})`, () => {
    it.each(['ready', 'failed'] as const)(
      '%s keeps its text above the native action, which opens the same meeting and dismisses',
      async status => {
        const { user } = await mount(sample.lng);
        const description =
          status === 'ready'
            ? 'Point de coordination des équipes internationales — décisions et prochaines étapes'
            : sample.failure;
        complete(
          meetingDetail({
            id: 'meeting-result',
            status,
            report: { title: description, participants: [], sections: [] },
            last_error_code: status === 'failed' ? 'synthesis_failed' : null,
          })
        );
        const title = await screen.findByText(status === 'ready' ? sample.ready : sample.failed);
        const notification = title.closest('[data-sonner-toast]');
        if (!(notification instanceof HTMLElement))
          throw new Error('No native Sonner notification');
        expect(within(notification).getByText(description)).toBeVisible();
        const action = within(notification).getByRole('button', {
          name: sample.action,
        });
        const content = title.parentElement;
        if (!content) throw new Error('No notification content');
        // Computed placement catches the original horizontal competition; real geometry is a browser check.
        expect(getComputedStyle(notification).display).toBe('grid');
        expect(getComputedStyle(content).gridRow).toBe('1');
        expect(getComputedStyle(action).gridColumn).toBe('1 / -1');
        expect(getComputedStyle(notification).paddingRight).toBe('16px');
        const close = within(notification).getByRole('button', { name: sample.close });
        expect(getComputedStyle(close).position).toBe('absolute');
        expect(getComputedStyle(close).top).toBe('4px');
        expect(getComputedStyle(close).transform).toBe('none');
        expect(notification.closest('[aria-live]')).toHaveAttribute('aria-live', 'polite');
        close.focus();
        await user.tab();
        expect(action).toHaveFocus();
        await user.keyboard('{Enter}');
        expect(push).toHaveBeenCalledExactlyOnceWith(
          '/dashboard/meetings/meeting-result?from=settings'
        );
        await waitFor(() => expect(notification).not.toBeInTheDocument());
      }
    );

    it('closes from the keyboard without opening the minutes', async () => {
      const { user } = await mount(sample.lng);
      complete(meetingDetail());
      const close = await screen.findByRole('button', { name: sample.close });
      const notification = close.closest('[data-sonner-toast]');
      close.focus();
      await user.keyboard(' ');
      await waitFor(() => expect(notification).not.toBeInTheDocument());
      expect(push).not.toHaveBeenCalled();
    });
  });
}

it('keeps a notification without an action on its existing layout', async () => {
  await mount('en');
  act(() => {
    toast.success('Copied');
  });
  const title = await screen.findByText('Copied');
  const notification = title.closest('[data-sonner-toast]');
  if (!(notification instanceof HTMLElement)) throw new Error('No native Sonner notification');
  expect(getComputedStyle(notification).display).toBe('flex');
  expect(getComputedStyle(notification).paddingRight).toBe('56px');
});
it('supports an action without an icon and keeps cancel before action in the keyboard order', async () => {
  const { user } = await mount('en');
  const confirm = vi.fn();
  const cancel = vi.fn();
  const label = 'Open the minutes for the international coordination meeting and its next steps';
  act(() => {
    toast('A notification without an icon', {
      description: 'A long description remains readable independently of the action label.',
      cancel: { label: 'Cancel', onClick: cancel },
      action: { label, onClick: confirm },
    });
  });
  const title = await screen.findByText('A notification without an icon');
  const content = title.parentElement;
  if (!content) throw new Error('No notification content');
  expect(getComputedStyle(content).gridColumn).toBe('1 / -1');
  const action = screen.getByRole('button', { name: label });
  expect(getComputedStyle(action).maxWidth).toBe('100%');
  expect(getComputedStyle(action).whiteSpace).toBe('normal');
  screen.getByRole('button', { name: 'Close' }).focus();
  await user.tab();
  const cancelButton = screen.getByRole('button', { name: 'Cancel' });
  expect(cancelButton).toHaveFocus();
  await user.tab();
  expect(action).toHaveFocus();
  await user.tab({ shift: true });
  await user.keyboard('{Enter}');
  expect(cancel).toHaveBeenCalledOnce();
  expect(confirm).not.toHaveBeenCalled();
  await waitFor(() => expect(title).not.toBeInTheDocument());
});
