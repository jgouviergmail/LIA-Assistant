/**
 * An answer's data cards fold under one « Show details » disclosure.
 *
 * The words stay visible; the cards the response node appended after them are
 * closed by default, open on the summary (pointer or keyboard), and open by
 * themselves when a history search matches inside them. Whatever the split
 * refuses — cards alone, a HITL draft card, plain prose — renders unchanged.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AssistantMessageBody } from '../AssistantMessageBody';

const locale = vi.hoisted(() => ({ language: 'en' }));
vi.mock('react-i18next', async () => {
  const en = (await import('../../../../locales/en/translation.json')).default.chat.card_group;
  const fr = (await import('../../../../locales/fr/translation.json')).default.chat.card_group;
  return {
    useTranslation: () => ({
      t: (key: string) => {
        const resource: Record<string, string> = locale.language === 'fr' ? fr : en;
        return resource[key.replace('chat.card_group.', '')] ?? key;
      },
      i18n: { language: locale.language },
    }),
  };
});

const PROSE = 'Here are your two unread emails.';
const CARD =
  '<div class="lia-card-binding" data-card-ref="m1"><hr class="lia-response-separator">' +
  '<div class="lia-response-wrapper" data-card-version="2"><div class="lia-card lia-email">' +
  '<p>Your booking is confirmed.</p></div></div></div>';

beforeEach(() => {
  locale.language = 'en';
});

describe('AssistantMessageBody', () => {
  it.each([
    { language: 'en', name: 'Show details' },
    { language: 'fr', name: 'Voir le détail' },
  ])('folds the cards under a closed, translated disclosure ($language)', sample => {
    locale.language = sample.language;
    const { container } = render(<AssistantMessageBody content={`${PROSE}\n\n${CARD}`} />);

    expect(screen.getByText(PROSE)).toBeVisible();
    const summary = screen.getByText(sample.name);
    expect(summary.closest('summary')).not.toBeNull();
    expect(container.querySelector('details')?.open).toBe(false);
    expect(screen.queryByText('Your booking is confirmed.')).not.toBeInTheDocument();
  });

  it('opens on a click and again closes', async () => {
    const user = userEvent.setup();
    render(<AssistantMessageBody content={`${PROSE}\n\n${CARD}`} />);

    await user.click(screen.getByText('Show details'));
    expect(screen.getByText('Your booking is confirmed.')).toBeVisible();

    await user.click(screen.getByText('Show details'));
    expect(screen.queryByText('Your booking is confirmed.')).not.toBeInTheDocument();
  });

  it('is a native disclosure the keyboard reaches', async () => {
    // Enter/Space activation is the browser's own <summary> behaviour, which
    // jsdom does not run: it is exercised in chat-answer-actions.spec.ts.
    const user = userEvent.setup();
    render(<AssistantMessageBody content={`${PROSE}\n\n${CARD}`} />);

    await user.tab();
    const summary = screen.getByText('Show details').closest('summary');
    expect(summary).toHaveFocus();
    expect(summary?.parentElement?.tagName).toBe('DETAILS');
  });

  it('opens by itself when a history search matches inside the cards', () => {
    const { container } = render(
      <AssistantMessageBody content={`${PROSE}\n\n${CARD}`} searchHighlight="BOOKING" />
    );

    const details = container.querySelector('details');
    expect(details?.open).toBe(true);
    expect(details).toHaveTextContent('Your booking is confirmed.');
    expect(details?.querySelector('mark')).toHaveTextContent('booking');
  });

  it('stays closed when the search only matches the words', () => {
    render(<AssistantMessageBody content={`${PROSE}\n\n${CARD}`} searchHighlight="unread" />);

    expect(screen.queryByText('Your booking is confirmed.')).not.toBeInTheDocument();
  });

  it.each([
    ['cards alone', CARD],
    ['a HITL draft card', '<div class="lia-card lia-draft"><p>To: camille@example.test</p></div>'],
    ['plain prose', PROSE],
  ])('renders %s unchanged, with no disclosure', (_label, content) => {
    const { container } = render(<AssistantMessageBody content={content} />);

    expect(container.querySelector('details')).toBeNull();
    expect(screen.queryByText('Show details')).not.toBeInTheDocument();
  });
});
