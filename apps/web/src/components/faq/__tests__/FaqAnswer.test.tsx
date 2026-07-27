/**
 * FaqAnswer (W1) — a written example becomes a real intent.
 *
 * The splitter is proven elsewhere (`faq-examples.test.ts` on rules,
 * `faq-examples.corpus.test.ts` on the 222 authored questions). What is proven
 * here is the rendering contract: the surrounding HTML survives untouched, the
 * commands become NATIVE buttons — nameable, focusable, keyboard-activatable —
 * and the phrase handed back is the one the user read.
 */

import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

// The global stub echoes the key, which would make the accessible-name test
// vacuous. Translation goes through the REAL French resource instead, so the
// test fails if `faq.try_example` is ever removed or loses its placeholder —
// an oracle no hand-copied dictionary would give.
const { translate } = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- vi.hoisted runs before ESM imports resolve
  const fr = require('../../../../locales/fr/translation.json') as Record<string, unknown>;
  const lookup = (key: string): string => {
    const value = key.split('.').reduce<unknown>((node, part) => {
      if (node && typeof node === 'object' && part in node) {
        return (node as Record<string, unknown>)[part];
      }
      return undefined;
    }, fr);
    return typeof value === 'string' ? value : key;
  };
  return {
    translate: (key: string, params?: Record<string, unknown>) =>
      lookup(key).replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(params?.[name] ?? '')),
  };
});

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: 'fr', changeLanguage: vi.fn() },
  }),
}));

import { FaqAnswer } from '../FaqAnswer';

const ANSWER =
  '<strong>Gmail</strong><br>• "<em>Montre mes emails non lus</em>"<br>' +
  '• "<em>Réponds à Jean</em>"<br>Dites <em>le premier</em> pour choisir.';

describe('FaqAnswer — rendering', () => {
  it('renders the authored HTML, formatting included', () => {
    renderWithProviders(<FaqAnswer lng="fr" html={ANSWER} />);
    expect(screen.getByText('Gmail')).toBeInTheDocument();
    expect(screen.getByText(/pour choisir/)).toBeInTheDocument();
  });

  it('turns each bulleted example into a button', () => {
    renderWithProviders(<FaqAnswer lng="fr" html={ANSWER} onExampleClick={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Montre mes emails non lus/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Réponds à Jean/ })).toBeInTheDocument();
  });

  it('leaves inline emphasis inert', () => {
    // "le premier" is prose. A button there would be nonsense — and would send
    // two meaningless words to the model.
    renderWithProviders(<FaqAnswer lng="fr" html={ANSWER} onExampleClick={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /le premier/ })).not.toBeInTheDocument();
    expect(screen.getByText('le premier')).toBeInTheDocument();
  });

  it('renders nothing clickable without a handler', () => {
    // The public FAQ has no chat to send to: dangling buttons would be a lie.
    renderWithProviders(<FaqAnswer lng="fr" html={ANSWER} />);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByText('Montre mes emails non lus')).toBeInTheDocument();
  });

  it('keeps search highlighting intact', () => {
    // FAQContent hands over already-highlighted HTML when searching; the split
    // must not eat the <mark>.
    const highlighted = '<br>• "<em>Montre mes emails</em>"<br>Voir <mark>emails</mark> ici.';
    const { container } = renderWithProviders(
      <FaqAnswer lng="fr" html={highlighted} onExampleClick={vi.fn()} />
    );
    expect(container.querySelector('mark')).toHaveTextContent('emails');
  });
});

describe('FaqAnswer — acting on an example', () => {
  it('hands back exactly the phrase that was read', async () => {
    const onExampleClick = vi.fn();
    renderWithProviders(<FaqAnswer lng="fr" html={ANSWER} onExampleClick={onExampleClick} />);

    await userEvent.click(screen.getByRole('button', { name: /Montre mes emails non lus/ }));

    expect(onExampleClick).toHaveBeenCalledWith('Montre mes emails non lus');
  });

  it('is reachable and activatable from the keyboard', async () => {
    const onExampleClick = vi.fn();
    renderWithProviders(
      <FaqAnswer lng="fr" html='• "<em>Une commande</em>"' onExampleClick={onExampleClick} />
    );

    const button = screen.getByRole('button', { name: /Une commande/ });
    button.focus();
    expect(button).toHaveFocus();
    await userEvent.keyboard('{Enter}');

    expect(onExampleClick).toHaveBeenCalledWith('Une commande');
  });

  it('names the action beyond the phrase itself', async () => {
    // "Trouve le contact de Jean" alone does not tell a screen reader user what
    // pressing it does.
    renderWithProviders(
      <FaqAnswer lng="fr" html='• "<em>Une commande</em>"' onExampleClick={vi.fn()} />
    );
    const name = screen.getByRole('button').getAttribute('aria-label') ?? '';
    expect(name).toContain('Une commande');
    expect(name.length).toBeGreaterThan('Une commande'.length);
    // The i18n key must resolve, not leak through as a raw key.
    expect(name).not.toContain('faq.try_example');
  });

  it('sends the decoded phrase, not its HTML entities', async () => {
    const onExampleClick = vi.fn();
    renderWithProviders(
      <FaqAnswer
        lng="fr"
        html={'• "<em>Quel est l&#39;email de Jean ?</em>"'}
        onExampleClick={onExampleClick}
      />
    );
    await userEvent.click(screen.getByRole('button'));
    expect(onExampleClick).toHaveBeenCalledWith("Quel est l'email de Jean ?");
  });

  it('acts once per click', async () => {
    const onExampleClick = vi.fn();
    renderWithProviders(
      <FaqAnswer lng="fr" html='• "<em>Une commande</em>"' onExampleClick={onExampleClick} />
    );
    await userEvent.click(screen.getByRole('button'));
    expect(onExampleClick).toHaveBeenCalledTimes(1);
  });

  it('does not submit an enclosing form', () => {
    // The FAQ page carries a search input; a default-type button inside a form
    // would reload the page instead of opening the chat.
    renderWithProviders(
      <FaqAnswer lng="fr" html='• "<em>Une commande</em>"' onExampleClick={vi.fn()} />
    );
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });
});
