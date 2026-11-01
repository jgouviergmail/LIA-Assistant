/**
 * The « Tools » lights screen (ADR-369, Task 9.2): each lamp's controls are
 * what it can do; a slider is SENT when it is released, never while it moves;
 * a refused change shows the previous value again and says why; a room and a
 * scene have their own gestures.
 */

import { fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen, waitFor, within } from '@/__tests__/test-utils';
import type { AppConfig } from '@/hooks/useAppConfig';
import { ApiError } from '@/lib/api-client';
import type {
  WorkbenchAvailability,
  WorkbenchLights,
  WorkbenchToolState,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  media: { desktop: true },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/en/dashboard/tools/lights',
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => media.desktop }));
vi.mock('@/hooks/useAppConfig', async importOriginal => ({
  ...(await importOriginal<typeof import('@/hooks/useAppConfig')>()),
  useAppConfig: () => ({
    config: { features: { workbench_enabled: true }, capabilities: {} } satisfies ShellConfig,
    loading: false,
    error: null,
  }),
}));

import { WorkbenchShell } from '../../WorkbenchShell';
import { LightsTool } from '../LightsTool';

function rail(state: WorkbenchToolState = 'ready'): WorkbenchAvailability {
  return {
    tools: [
      {
        tool: 'lights',
        state,
        provider: state === 'ready' ? 'philips_hue' : null,
        features: state === 'ready' ? ['scenes'] : [],
        bounds: {},
      },
    ],
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      calendar_window_max_events: 500,
    },
  };
}

const BRIDGE: WorkbenchLights = {
  rooms: [{ id: 'r1', name: 'Living room', light_ids: ['sofa', 'hall', 'plug'], on: true }],
  lights: [
    {
      id: 'sofa',
      name: 'Sofa',
      room_id: 'r1',
      on: true,
      brightness: 62,
      supports_color: true,
      color_hex: '#ff3b30',
      mirek: 366,
      mirek_min: 153,
      mirek_max: 500,
    },
    {
      id: 'hall',
      name: 'Hall',
      room_id: 'r1',
      on: false,
      brightness: 100,
      supports_color: false,
      color_hex: null,
      mirek: null,
      mirek_min: null,
      mirek_max: null,
    },
    {
      id: 'plug',
      name: 'Plug',
      room_id: 'r1',
      on: true,
      brightness: null,
      supports_color: false,
      color_hex: null,
      mirek: null,
      mirek_min: null,
      mirek_max: null,
    },
  ],
  scenes: [{ id: 's1', name: 'Relax', room_id: 'r1', active: false }],
};

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  media.desktop = true;
  api.get.mockImplementation((path: string) =>
    Promise.resolve(path === '/workbench' ? rail() : BRIDGE)
  );
  api.post.mockResolvedValue(undefined);
});

function screenOf() {
  return renderWithProviders(
    <WorkbenchShell lng="en">
      <LightsTool lng="en" />
    </WorkbenchShell>
  );
}

function lampCard(name: string): HTMLElement {
  const card = screen.getByRole('group', { name });
  return card;
}

describe('LightsTool', () => {
  it('draws each lamp with the controls it can take', async () => {
    const { user } = screenOf();
    await screen.findByRole('group', { name: 'Sofa' });

    const sofa = lampCard('Sofa');
    expect(within(sofa).getByRole('slider', { name: 'workbench.lights.brightness' })).toBeVisible();
    await user.click(within(sofa).getByText('workbench.lights.tone'));
    const temperature = within(sofa).getByRole('slider', { name: 'workbench.lights.temperature' });
    // The colour is the lamp's current colour alone, its panel the choice (owner, 2026-10-31):
    // no row of swatches, and the temperature comes first.
    const colour = within(sofa).getByLabelText('workbench.lights.colour');
    expect(colour).toHaveAttribute('type', 'color');
    expect(colour).toHaveValue('#ff3b30');
    expect(within(sofa).queryAllByRole('button')).toEqual([]);
    expect(
      temperature.compareDocumentPosition(colour) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    const hall = lampCard('Hall');
    expect(within(hall).getByRole('slider', { name: 'workbench.lights.brightness' })).toBeVisible();
    expect(within(hall).queryByRole('slider', { name: 'workbench.lights.temperature' })).toBeNull();
    expect(within(hall).queryByLabelText('workbench.lights.colour')).toBeNull();

    expect(within(lampCard('Plug')).queryByRole('slider')).toBeNull();
  });

  /** Owner request (2026-10-31): the temperature and the colour fold away until opened. */
  it("folds a lamp's temperature and colour until opened, its current tone said while folded", async () => {
    const { user } = screenOf();
    await screen.findByRole('group', { name: 'Sofa' });
    const sofa = lampCard('Sofa');

    expect(within(sofa).queryByRole('slider', { name: 'workbench.lights.temperature' })).toBeNull();
    expect(within(sofa).queryByLabelText('workbench.lights.colour')).toBeNull();
    // Folded, the section still says the tone: the temperature, and the colour as a dot.
    const summary = within(sofa).getByText('workbench.lights.tone').closest('summary');
    expect(summary).not.toBeNull();
    expect(within(summary as HTMLElement).getByText('workbench.lights.kelvin')).toBeVisible();
    expect(
      (summary as HTMLElement).querySelector('[data-tone-colour]')?.getAttribute('style')
    ).toContain('rgb(255, 59, 48)');

    await user.click(within(sofa).getByText('workbench.lights.tone'));
    expect(
      within(sofa).getByRole('slider', { name: 'workbench.lights.temperature' })
    ).toBeVisible();
    expect(within(sofa).getByLabelText('workbench.lights.colour')).toHaveValue('#ff3b30');

    // A lamp that takes neither has no such section at all.
    expect(lampCard('Hall').querySelector('details')).toBeNull();
  });

  /** Owner request (2026-10-31): rooms and lamps in alphabetical order. */
  it("draws the open room's lamps in alphabetical order", async () => {
    screenOf();
    await screen.findByRole('group', { name: 'Sofa' });

    const lamps = screen
      .getAllByRole('group')
      .map(group => group.getAttribute('aria-label'))
      .filter(name => name === 'Sofa' || name === 'Hall' || name === 'Plug');
    expect(lamps).toEqual(['Hall', 'Plug', 'Sofa']);
  });

  it('lists the rooms in alphabetical order, and opens the first of them beside the list', async () => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(
        path === '/workbench'
          ? rail()
          : {
              ...BRIDGE,
              rooms: [
                { id: 'r2', name: 'Salon', light_ids: ['hall'], on: true },
                { id: 'r1', name: 'Cuisine', light_ids: ['sofa', 'plug'], on: true },
              ],
            }
      )
    );
    screenOf();
    await screen.findByRole('group', { name: 'Sofa' });

    const rooms = screen
      .getAllByRole('link')
      .map(link => link.textContent ?? '')
      .filter(text => text.startsWith('Cuisine') || text.startsWith('Salon'));
    expect(rooms.map(text => text.slice(0, 5))).toEqual(['Cuisi', 'Salon']);
    expect(screen.queryByRole('group', { name: 'Hall' })).toBeNull();
  });

  it('sends a slider when it is released, never while it moves', async () => {
    screenOf();
    await screen.findByRole('group', { name: 'Sofa' });
    const slider = within(lampCard('Sofa')).getByRole('slider', {
      name: 'workbench.lights.brightness',
    });

    fireEvent.input(slider, { target: { value: '30' } });
    expect(api.post).not.toHaveBeenCalled();

    fireEvent.change(slider, { target: { value: '30' } });
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/light',
        { light_id: 'sofa', brightness: 30 },
        undefined
      )
    );
  });

  it('sends a colour when its panel closes, never while it moves', async () => {
    const { user } = screenOf();
    await screen.findByRole('group', { name: 'Sofa' });
    await user.click(within(lampCard('Sofa')).getByText('workbench.lights.tone'));
    const colour = within(lampCard('Sofa')).getByLabelText('workbench.lights.colour');

    fireEvent.input(colour, { target: { value: '#00ff00' } });
    expect(api.post).not.toHaveBeenCalled();
    expect(colour).toHaveValue('#00ff00');

    fireEvent.change(colour, { target: { value: '#00ff00' } });
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/light',
        { light_id: 'sofa', color_hex: '#00ff00' },
        undefined
      )
    );
  });

  it('shows the previous value again when a change is refused, and says why', async () => {
    api.post.mockRejectedValueOnce(
      new ApiError('refused', 502, { detail: { code: 'provider_unavailable' } })
    );
    screenOf();
    await screen.findByRole('group', { name: 'Sofa' });
    const slider = within(lampCard('Sofa')).getByRole('slider', {
      name: 'workbench.lights.brightness',
    });

    fireEvent.change(slider, { target: { value: '30' } });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.errors.provider_unavailable')
    );
    await waitFor(() => expect(slider).toHaveValue('62'));
  });

  it('switches a whole room, and shows a scene', async () => {
    const { user } = screenOf();
    await screen.findByRole('group', { name: 'Sofa' });

    await user.click(screen.getByRole('switch', { name: 'workbench.lights.room_switch' }));
    await user.click(screen.getByRole('button', { name: 'Relax' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/room',
        { room_id: 'r1', on: false },
        undefined
      )
    );
    expect(api.post).toHaveBeenCalledWith('/workbench/lights/scene', { scene_id: 's1' }, undefined);
  });

  it('below lg, hands the focus to the room that replaces the list, then back to its card', async () => {
    media.desktop = false;
    const tree = () => (
      <WorkbenchShell lng="en">
        <LightsTool lng="en" />
      </WorkbenchShell>
    );
    const { rerender } = renderWithProviders(tree());
    await screen.findByRole('link', { name: /Living room/ });

    nav.search = 'room=r1';
    rerender(tree());
    const back = await screen.findByRole('link', { name: 'workbench.lights.back_to_rooms' });
    await waitFor(() => expect(back).toHaveFocus());

    nav.search = '';
    rerender(tree());
    await waitFor(() => expect(screen.getByRole('link', { name: /Living room/ })).toHaveFocus());
  });

  it('says what to do when no bridge is connected', async () => {
    api.get.mockImplementation((path: string) =>
      path === '/workbench'
        ? Promise.resolve(rail('not_connected'))
        : Promise.reject(new Error('no'))
    );
    screenOf();

    expect(await screen.findByText('workbench.states.not_connected_title')).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/workbench/lights', expect.anything());
  });
});
