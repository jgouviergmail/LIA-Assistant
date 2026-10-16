import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import en from '@/../locales/en/translation.json';
import fr from '@/../locales/fr/translation.json';
const language = vi.hoisted(() => ({ value: 'en' }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const catalog = language.value === 'fr' ? fr : en;
      return key === 'common.show_more'
        ? catalog.common.show_more
        : key === 'common.show_less'
          ? catalog.common.show_less
          : key;
    },
  }),
}));
import { ExpandableDescription } from '../expandable-description';

afterEach(() => {
  document.body.onclick = null;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function measure(height: number) {
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(height);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(60);
  class Observer implements ResizeObserver {
    constructor(private callback: ResizeObserverCallback) {}
    observe() {
      this.callback([], this);
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', Observer);
}
describe('measured expandable descriptions', () => {
  it('offers no redundant toggle when the entire text fits', () => {
    measure(60);
    renderWithProviders(<ExpandableDescription text="A complete short description" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
  it('toggles the controlled text without opening the surrounding space', async () => {
    measure(120);
    const open = vi.fn();
    document.body.onclick = open;
    const { user } = renderWithProviders(<ExpandableDescription text="A longer description" />);
    const more = screen.getByRole('button', { name: en.common.show_more });
    expect(more).toHaveAttribute('aria-controls', screen.getByText('A longer description').id);
    await user.click(more);
    expect(screen.getByRole('button', { name: en.common.show_less })).toHaveAttribute(
      'aria-expanded',
      'true'
    );
    await user.click(screen.getByRole('button', { name: en.common.show_less }));
    expect(screen.getByRole('button', { name: en.common.show_more })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(open).not.toHaveBeenCalled();
  });
});

it.each(['en', 'fr'])('names both description controls in %s', async lng => {
  language.value = lng;
  measure(120);
  const catalog = lng === 'fr' ? fr : en;
  const { user } = renderWithProviders(<ExpandableDescription text="A long description" />);
  await user.click(screen.getByRole('button', { name: catalog.common.show_more }));
  expect(screen.getByRole('button', { name: catalog.common.show_less })).toHaveAttribute(
    'aria-expanded',
    'true'
  );
  language.value = 'en';
});
