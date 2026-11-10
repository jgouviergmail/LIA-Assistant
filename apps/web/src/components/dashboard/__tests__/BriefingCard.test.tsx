import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import { DEFAULT_ICON_STYLE, ICON_STYLES, type IconStyle } from '@/lib/icon-style';
import { IconStyleContext } from '@/lib/icon-style-context';
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

async function renderCard(
  cardProps: BriefingCardProps<AgendaData>,
  language: 'en' | 'fr' = 'en',
  iconStyle: IconStyle = DEFAULT_ICON_STYLE
) {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  const card = (nextProps: BriefingCardProps<AgendaData>) => (
    <I18nextProvider i18n={i18n}>
      <IconStyleContext.Provider value={iconStyle}>
        <BriefingCard {...nextProps} />
      </IconStyleContext.Provider>
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

  it.each(ICON_STYLES)(
    'keeps refresh visible without motion, focused and guarded with %s icons',
    async style => {
      const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
      const media = vi.spyOn(window, 'matchMedia').mockImplementation(query => ({
        ...mediaQuery,
        media: query,
        matches: query === '(prefers-reduced-motion: reduce)',
      }));
      try {
        const cardProps = props();
        const { user, rerenderCard } = await renderCard(cardProps, 'en', style);
        const refresh = screen.getByRole('button', { name: 'Refresh Agenda' });
        expect(refresh).toHaveAttribute('aria-busy', 'false');
        expect(refresh).not.toHaveClass('border-primary', 'bg-primary/10');
        expect(refresh.querySelector('svg')).toHaveAttribute('data-icon-style', style);
        await user.hover(refresh);
        expect(refresh).toHaveClass(
          'hover:bg-muted/60',
          'dark:hover:bg-[color-mix(in_srgb,var(--color-card)_75%,black)]'
        );
        expect(cardProps.onRefresh).not.toHaveBeenCalled();
        await user.tab();
        expect(refresh).toHaveFocus();
        await user.keyboard('{Enter}');
        expect(cardProps.onRefresh).toHaveBeenCalledTimes(1);

        rerenderCard({ ...cardProps, isRefreshing: true });
        expect(refresh).toHaveFocus();
        expect(refresh).toHaveAttribute('aria-disabled', 'true');
        expect(refresh).toHaveAttribute('aria-busy', 'true');
        expect(refresh).toHaveClass(
          'border-primary',
          'bg-primary/10',
          'dark:bg-[color-mix(in_srgb,var(--color-card)_75%,black)]'
        );
        expect(refresh).not.toBeDisabled();
        expect(screen.getByRole('region', { name: 'Agenda' })).toHaveAttribute('aria-busy', 'true');
        await user.keyboard('{Enter} ');
        await user.click(refresh);
        expect(cardProps.onRefresh).toHaveBeenCalledTimes(1);

        rerenderCard({ ...cardProps, isRefreshing: false });
        expect(refresh).toHaveFocus();
        expect(refresh).toHaveAttribute('aria-busy', 'false');
        expect(refresh).not.toHaveClass('border-primary', 'bg-primary/10');
        expect(refresh).toHaveClass(
          'dark:hover:bg-[color-mix(in_srgb,var(--color-card)_75%,black)]'
        );
        await user.keyboard('{Enter}');
        expect(cardProps.onRefresh).toHaveBeenCalledTimes(2);
      } finally {
        media.mockRestore();
      }
    }
  );

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

describe('BriefingCard « just updated » badge', () => {
  it('says « updated » once a refresh completes, then dates the data again', async () => {
    const cardProps = props();
    const { rerenderCard } = await renderCard(cardProps);
    const badge = en.dashboard.briefing.synthesis_updated_badge;
    vi.useFakeTimers();
    try {
      rerenderCard({ ...cardProps, isRefreshing: true });
      expect(screen.queryByText(badge)).not.toBeInTheDocument();

      rerenderCard({ ...cardProps, isRefreshing: false });

      expect(screen.getByText(badge)).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(1599));
      expect(screen.getByText(badge)).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(1));
      expect(screen.queryByText(badge)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('never says « updated » for a card that was not refreshed', async () => {
    const cardProps = props();
    const { rerenderCard } = await renderCard(cardProps);

    rerenderCard({ ...cardProps, section: section({ generated_at: '2026-10-15T06:05:00Z' }) });

    expect(
      screen.queryByText(en.dashboard.briefing.synthesis_updated_badge)
    ).not.toBeInTheDocument();
  });
});
