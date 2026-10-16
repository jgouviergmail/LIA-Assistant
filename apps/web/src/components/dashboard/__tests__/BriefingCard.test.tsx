import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import type { AgendaData, CardSection } from '@/types/briefing';
import { BriefingCard, type BriefingCardProps } from '../BriefingCard';

vi.unmock('react-i18next');

function section(overrides: Partial<CardSection<AgendaData>> = {}): CardSection<AgendaData> {
  return {
    status: 'ok',
    data: {
      events: Array.from({ length: 17 }, (_, index) => ({
        title: `Meeting ${index + 1}`,
        start_local: '14:00',
        end_local: null,
        location: null,
      })),
    },
    generated_at: '2026-10-15T06:00:00Z',
    error_code: null,
    error_message: null,
    from_cache: false,
    stale_generated_at: null,
    last_attempt_at: null,
    ...overrides,
  };
}

function props(
  overrides: Partial<BriefingCardProps<AgendaData>> = {}
): BriefingCardProps<AgendaData> {
  return {
    titleKey: 'dashboard.briefing.cards.agenda.title',
    icon: <span />,
    tone: 'violet',
    section: section(),
    isRefreshing: false,
    onRefresh: vi.fn(),
    emptyStateKey: 'dashboard.briefing.cards.agenda.empty',
    renderContent: data => (
      <>
        <label htmlFor="briefing-test-note">
          Personal note
          <input id="briefing-test-note" aria-label="Personal note" defaultValue="Keep this note" />
        </label>
        <ul>
          {data.events.map(event => (
            <li key={event.title}>{event.title}</li>
          ))}
        </ul>
      </>
    ),
    ...overrides,
  };
}

async function renderCard(cardProps: BriefingCardProps<AgendaData>, language: 'en' | 'fr' = 'en') {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  const card = (nextProps: BriefingCardProps<AgendaData>) => (
    <I18nextProvider i18n={i18n}>
      <BriefingCard {...nextProps} />
    </I18nextProvider>
  );
  const result = render(card(cardProps));
  return {
    ...result,
    user: userEvent.setup(),
    rerenderCard: (nextProps: BriefingCardProps<AgendaData>) => result.rerender(card(nextProps)),
  };
}

describe('BriefingCard content and refresh', () => {
  it('lets a keyboard reader focus the named content and keeps every supplied item', async () => {
    const { user } = await renderCard(props());
    const content = screen.getByRole('group', { name: 'Agenda' });
    await user.tab();
    expect(screen.getByRole('button', { name: 'Refresh Agenda' })).toHaveFocus();
    await user.tab();
    expect(content).toHaveFocus();
    expect(within(content).getAllByRole('listitem')).toHaveLength(17);
    expect(within(content).getByText('Meeting 17')).toBeVisible();
  });

  it('keeps refresh focused and keyboard reachable while preventing duplicate refreshes', async () => {
    const cardProps = props();
    const { user, rerenderCard } = await renderCard(cardProps);
    const refresh = screen.getByRole('button', { name: 'Refresh Agenda' });
    await user.tab();
    await user.keyboard('{Enter}');
    expect(cardProps.onRefresh).toHaveBeenCalledTimes(1);

    rerenderCard({ ...cardProps, isRefreshing: true });
    expect(refresh).toHaveFocus();
    expect(refresh).toHaveAttribute('aria-disabled', 'true');
    expect(refresh).not.toBeDisabled();
    expect(screen.getByRole('region', { name: 'Agenda' })).toHaveAttribute('aria-busy', 'true');
    await user.keyboard('{Enter} ');
    await user.click(refresh);
    expect(cardProps.onRefresh).toHaveBeenCalledTimes(1);

    rerenderCard({ ...cardProps, isRefreshing: false });
    expect(refresh).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(cardProps.onRefresh).toHaveBeenCalledTimes(2);
  });

  it('retains the mounted content, its draft and its position during a refresh', async () => {
    const cardProps = props();
    const { user, rerenderCard } = await renderCard(cardProps);
    const note = screen.getByRole('textbox', { name: 'Personal note' });
    await user.clear(note);
    await user.type(note, 'Draft in progress');
    const content = screen.getByRole('group', { name: 'Agenda' });
    content.scrollTop = 180;

    rerenderCard({ ...cardProps, isRefreshing: true });
    expect(screen.getByRole('textbox', { name: 'Personal note' })).toBe(note);
    expect(note).toHaveValue('Draft in progress');
    expect(note).toHaveFocus();
    expect(content.scrollTop).toBe(180);
    expect(within(content).getAllByRole('listitem')).toHaveLength(17);
  });

  it('preserves the draft and focused content when a provider returns stale data with an error', async () => {
    const cardProps = props();
    const { user, rerenderCard } = await renderCard(cardProps);
    const note = screen.getByRole('textbox', { name: 'Personal note' });
    await user.clear(note);
    await user.type(note, 'Keep this unsaved draft');
    rerenderCard({
      ...cardProps,
      section: section({
        status: 'error',
        error_code: 'connector_network',
        error_message: 'Offline',
      }),
    });
    expect(screen.getByRole('textbox', { name: 'Personal note' })).toBe(note);
    expect(note).toHaveValue('Keep this unsaved draft');
    expect(note).toHaveFocus();
    expect(screen.getByText('Offline')).toBeVisible();
  });

  it('preserves every stale item alongside the error, retry and original data timestamp', async () => {
    const retry = vi.fn();
    await renderCard(
      props({
        section: section({
          status: 'error',
          error_code: 'connector_network',
          error_message: 'Calendar unavailable',
          stale_generated_at: '2026-10-14T06:00:00Z',
          last_attempt_at: '2026-10-15T06:00:00Z',
        }),
        onRefresh: retry,
      })
    );
    expect(screen.getByText('Calendar unavailable')).toBeVisible();
    expect(screen.getAllByRole('listitem')).toHaveLength(17);
    expect(screen.getByText('Meeting 17')).toBeVisible();
    expect(document.querySelector('time')).toHaveAttribute('dateTime', '2026-10-14T06:00:00Z');
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('keeps the named card as a focus destination when the last item disappears', async () => {
    const cardProps = props();
    const { rerenderCard } = await renderCard(cardProps);
    const region = screen.getByRole('region', { name: 'Agenda' });
    region.focus();
    rerenderCard({ ...cardProps, section: section({ status: 'empty', data: null }) });
    expect(region).toHaveFocus();
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument();
    expect(screen.getByText(en.dashboard.briefing.cards.agenda.empty)).toBeVisible();
  });

  it('does not show a card with no configured source', async () => {
    await renderCard(props({ section: section({ status: 'not_configured', data: null }) }));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it.each([
    ['en', 'Refresh Agenda'],
    ['fr', 'Rafraîchir Agenda'],
  ] as const)('gives refresh its real localized accessible name in %s', async (language, label) => {
    const { user } = await renderCard(props(), language);
    const refresh = screen.getByRole('button', { name: label });
    expect(refresh).toBeVisible();
    await user.tab();
    expect(refresh).toHaveFocus();
  });
});

describe('BriefingCard error recovery', () => {
  it.each(['connector_network', 'connector_rate_limit'])(
    'retries %s without opening connector settings',
    async code => {
      const onRefresh = vi.fn();
      const onErrorCta = vi.fn();
      await renderCard(
        props({
          section: section({ status: 'error', error_code: code, error_message: 'Offline' }),
          onRefresh,
          onErrorCta,
        })
      );
      const name =
        code === 'connector_network'
          ? en.dashboard.briefing.actions.retry
          : en.dashboard.briefing.actions.retry_later;
      await userEvent.click(screen.getByRole('button', { name }));
      expect(onRefresh).toHaveBeenCalledTimes(1);
      expect(onErrorCta).not.toHaveBeenCalled();
    }
  );

  it('keeps the reconnect action for expired authorization', async () => {
    const onRefresh = vi.fn();
    const onErrorCta = vi.fn();
    await renderCard(
      props({
        section: section({ status: 'error', error_code: 'connector_oauth_expired' }),
        onRefresh,
        onErrorCta,
      })
    );
    await userEvent.click(
      screen.getByRole('button', { name: en.dashboard.briefing.actions.reconnect })
    );
    expect(onErrorCta).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});

describe('BriefingCard recovery focus', () => {
  it('returns focus to the stable refresh control when successful recovery removes the retry button', async () => {
    const cardProps = props({
      section: section({ status: 'error', error_code: 'connector_network' }),
    });
    const { user, rerenderCard } = await renderCard(cardProps);
    await user.click(screen.getByRole('button', { name: en.dashboard.briefing.actions.retry }));
    rerenderCard({ ...cardProps, section: section() });
    expect(screen.getByRole('button', { name: 'Refresh Agenda' })).toHaveFocus();
  });
});
