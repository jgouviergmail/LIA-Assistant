import { lazy, Suspense, type ComponentType } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { WorldNativePanel } from '../WorldNativePanel';

const state = vi.hoisted(() => ({ id: 'owner', is_active: true }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: state }) }));
vi.mock('@/hooks/useSettingsAvailability', () => ({
  useSettingsAvailability: () => ({ isSuperuser: false }),
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/dynamic', () => ({
  default: (load: () => Promise<ComponentType<Record<string, unknown>>>) => {
    const Loaded = lazy(async () => ({ default: await load() }));
    return function DynamicContent(props: Record<string, unknown>) {
      return (
        <Suspense fallback="Loading native">
          <Loaded {...props} />
        </Suspense>
      );
    };
  },
}));
vi.mock('@/components/chat/ChatWorkspace', () => ({
  ChatWorkspace: ({ embedded, openingDraft }: { embedded: boolean; openingDraft?: string }) => (
    <input
      aria-label={embedded ? 'Private composer' : 'Page composer'}
      defaultValue={openingDraft}
    />
  ),
}));
vi.mock('@/components/settings/GeneratedAssetsSettings', () => ({
  GeneratedAssetsSettings: ({ initialTab }: { initialTab: string }) => <p>Gallery {initialTab}</p>,
}));
vi.mock('@/components/settings/SettingsPaneFrame', () => ({
  SettingsPaneFrame: ({
    token,
    onBack,
    showBack,
  }: {
    token: string;
    onBack(): void;
    showBack: boolean;
  }) => (
    <div>
      Native {token}
      <button onClick={onBack}>Close native</button>
      <span>{showBack ? 'Nested back' : 'Host owns back'}</span>
    </div>
  ),
}));
beforeEach(() => {
  state.id = 'owner';
  state.is_active = true;
});
const props = { lng: 'fr' as const, ownerId: 'owner', onBack: vi.fn() };

it('prefills an editable unsent embedded draft and forgets it on authority loss', async () => {
  const view = render(<WorldNativePanel {...props} selection="lia" openingDraft="Appelle " />);
  const editor = await screen.findByRole('textbox', { name: 'Private composer' });
  expect(editor).toHaveValue('Appelle ');
  fireEvent.change(editor, { target: { value: 'Private unfinished draft' } });
  state.id = 'peer';
  view.rerender(<WorldNativePanel {...props} selection="lia" />);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  state.id = 'owner';
  view.rerender(<WorldNativePanel {...props} selection="lia" />);
  expect(await screen.findByRole('textbox')).toHaveValue('');
});

it('opens the explicit asset family, then delegates ordinary native navigation to its existing frame', async () => {
  const view = render(
    <WorldNativePanel {...props} selection="generated-assets" galleryTab="documents" />
  );
  expect(await screen.findByText('Gallery documents')).toBeVisible();
  view.rerender(<WorldNativePanel {...props} selection="generated-assets" galleryTab="images" />);
  expect(await screen.findByText('Gallery images')).toBeVisible();
  view.rerender(<WorldNativePanel {...props} selection="memories" />);
  expect(screen.getByText('Native memories')).toBeVisible();
  expect(screen.getByText('Host owns back')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Close native' }));
  expect(props.onBack).toHaveBeenCalledTimes(1);
});

it('refuses administrative and disabled panels even when called directly', () => {
  const view = render(<WorldNativePanel {...props} selection="admin-users" />);
  expect(screen.getByRole('status')).toHaveTextContent('world.functions.unavailable');
  view.rerender(<WorldNativePanel {...props} selection="open-loops" />);
  expect(screen.getByRole('status')).toHaveTextContent('world.functions.unavailable');
  state.is_active = false;
  view.rerender(<WorldNativePanel {...props} selection="memories" />);
  expect(view.container).toBeEmptyDOMElement();
});
