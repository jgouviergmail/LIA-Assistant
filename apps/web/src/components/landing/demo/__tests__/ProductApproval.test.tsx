import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import en from '../../../../../locales/en/translation.json';
import fr from '../../../../../locales/fr/translation.json';
import { ProductApproval } from '../ProductApproval';

const resources = { en, fr };
const locale = vi.hoisted<{ language: 'en' | 'fr' }>(() => ({ language: 'en' }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      let value: unknown = locale.language === 'fr' ? fr : en;
      for (const part of key.split('.')) {
        if (typeof value !== 'object' || value === null || !(part in value)) return key;
        value = Reflect.get(value, part);
      }
      return typeof value === 'string' ? value : key;
    },
    i18n: { language: locale.language },
  }),
}));

const fetchRequest = vi.fn();
const xhrRequest = vi.fn<XMLHttpRequest['send']>();

beforeEach(() => {
  fetchRequest.mockClear();
  xhrRequest.mockClear();
  vi.stubGlobal('fetch', fetchRequest);
  vi.spyOn(XMLHttpRequest.prototype, 'send').mockImplementation(xhrRequest);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ProductApproval', () => {
  it('uses the native draft edit form without executing or pretending to regenerate a call', async () => {
    locale.language = 'en';
    const user = userEvent.setup();
    render(<ProductApproval />);
    await user.click(screen.getByRole('button', { name: en.chat.hitl.actions.edit }));
    const instructions = screen.getByRole('textbox', { name: en.chat.hitl.edit.placeholder });
    await user.type(instructions, 'Ask for an indoor table instead.');
    await user.click(screen.getByRole('button', { name: en.chat.hitl.edit.submit }));
    expect(screen.getByText('Ask for an indoor table instead.')).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent(
      en.landing.home_product_demo.approval_edited
    );
    expect(
      screen.getByRole('button', { name: en.landing.home_product_demo.approval_reset })
    ).toHaveFocus();
    expect(fetchRequest).not.toHaveBeenCalled();
    expect(xhrRequest).not.toHaveBeenCalled();
  });
  it.each(['en', 'fr'] as const)(
    'shows the localized real approval card and the specific fictional call in %s',
    async language => {
      locale.language = language;
      const copy = resources[language];
      const call = copy.landing.home_product_demo.scenes.call;
      render(<ProductApproval />);

      const card = screen.getByRole('region', { name: copy.chat.hitl.title.draft_critique });
      // The production renderer is lazy-loaded; a cold parallel run must
      // await its content rather than mistake the import delay for a result.
      expect(
        await screen.findByText('Les Jardins (Demo)', { exact: true }, { timeout: 5_000 })
      ).toBeVisible();
      // The production Markdown renderer applies its real phone formatter.
      expect(screen.getByText('(202) 555-0100', { exact: false })).toBeVisible();
      expect(screen.getByText(call.result_3, { exact: false })).toBeVisible();
      expect(
        within(card).getByRole('button', { name: copy.chat.hitl.actions.confirm })
      ).toBeVisible();
      expect(
        within(card).getByRole('button', { name: copy.chat.hitl.actions.cancel })
      ).toBeVisible();
      expect(within(card).getByRole('button', { name: copy.chat.hitl.actions.edit })).toBeVisible();
      expect(screen.getByText(copy.landing.home_product_demo.approval_hint)).toBeVisible();
      expect(screen.getByRole('status')).toBeEmptyDOMElement();
      expect(fetchRequest).not.toHaveBeenCalled();
      expect(xhrRequest).not.toHaveBeenCalled();
    }
  );

  it.each(['en', 'fr'] as const)(
    'confirms, resets and declines with keyboard focus preserved and no network request in %s',
    async language => {
      locale.language = language;
      const copy = resources[language];
      const user = userEvent.setup();
      render(<ProductApproval />);

      const confirm = screen.getByRole('button', { name: copy.chat.hitl.actions.confirm });
      const reset = screen.getByRole('button', {
        name: copy.landing.home_product_demo.approval_reset,
      });
      confirm.focus();
      await user.keyboard('{Enter}');

      expect(screen.getByText(copy.chat.hitl.resolved.confirmed)).toBeVisible();
      expect(screen.getByRole('status')).toHaveTextContent(
        copy.landing.home_product_demo.approval_confirmed
      );
      expect(
        screen.queryByRole('button', { name: copy.chat.hitl.actions.confirm })
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: copy.chat.hitl.actions.cancel })
      ).not.toBeInTheDocument();
      expect(reset).toHaveFocus();

      await user.keyboard('{Enter}');
      expect(screen.getByRole('status')).toBeEmptyDOMElement();
      expect(screen.queryByText(copy.chat.hitl.resolved.confirmed)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: copy.chat.hitl.actions.confirm })).toBeVisible();
      expect(reset).toHaveFocus();
      await user.tab({ shift: true });
      expect(screen.getByRole('button', { name: copy.chat.hitl.actions.cancel })).toHaveFocus();
      await user.keyboard(' ');

      expect(screen.getByText(copy.chat.hitl.resolved.cancelled)).toBeVisible();
      expect(screen.getByRole('status')).toHaveTextContent(
        copy.landing.home_product_demo.approval_cancelled
      );
      expect(reset).toHaveFocus();
      expect(
        screen.queryByRole('button', { name: copy.chat.hitl.actions.confirm })
      ).not.toBeInTheDocument();
      expect(fetchRequest).not.toHaveBeenCalled();
      expect(xhrRequest).not.toHaveBeenCalled();
    }
  );
});
