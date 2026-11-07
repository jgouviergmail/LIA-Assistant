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
  WorkbenchRoom,
  WorkbenchToolState,
} from '@/lib/workbench/types';

type ShellConfig = Pick<AppConfig, 'capabilities'> & { features: { workbench_enabled?: boolean } };

const { api, nav, toast, media, openChat } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  nav: { search: '', push: vi.fn(), replace: vi.fn() },
  toast: { error: vi.fn(), success: vi.fn() },
  media: { desktop: true },
  openChat: vi.fn(),
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/chat-deep-link', () => ({ openChatDeepLink: openChat }));
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
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
      assist_text_max_chars: 8000,
      assist_instruction_max_chars: 500,
    },
  };
}

const PLAIN_ROOM = {
  kind: 'room',
  supports_color: false,
  mirek_min: null,
  mirek_max: null,
} as const;
const STILL = { dynamic: false, playing: false };

const BRIDGE: WorkbenchLights = {
  rooms: [
    { id: 'r1', name: 'Living room', light_ids: ['sofa', 'hall', 'plug'], on: true, ...PLAIN_ROOM },
  ],
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
      reachable: null,
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
      reachable: null,
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
      reachable: null,
    },
  ],
  scenes: [{ id: 's1', name: 'Relax', room_id: 'r1', active: false, ...STILL }],
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

describe('LightsTool — the question to LIA', () => {
  it('ends the open room’s title, as every detail’s bar does, and sends nothing', async () => {
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.ask.label' }));

    expect(openChat).toHaveBeenCalledWith('/en/dashboard/chat');
    expect(window.localStorage.getItem('lia.chatDraft.owner')).toBe('workbench.ask.lights');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('leaves the words of a schedule in the chat: routines are the assistant’s', async () => {
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.ask.label' }));
    await user.click(await screen.findByRole('menuitem', { name: 'workbench.ask.ready.lights' }));

    expect(window.localStorage.getItem('lia.chatDraft.owner')).toContain(
      'workbench.ask.ready.lights_words'
    );
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('LightsTool — everything off', () => {
  const allOff = () => screen.findByRole('button', { name: 'workbench.lights.all_off' });
  const bridgeIs = (bridge: WorkbenchLights) =>
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : bridge)
    );
  const bridgeReads = () =>
    api.get.mock.calls.filter(([path]) => path === '/workbench/lights').length;
  const lit = (): WorkbenchLights => ({
    ...BRIDGE,
    rooms: [
      { id: 'r1', name: 'Living room', light_ids: ['sofa'], on: true, ...PLAIN_ROOM },
      { id: 'r2', name: 'Bedroom', light_ids: [], on: false, ...PLAIN_ROOM },
    ],
    lights: [
      ...BRIDGE.lights.filter(item => item.id === 'sofa'),
      { ...BRIDGE.lights[0], id: 'porch', name: 'Porch', room_id: null, on: true },
    ],
  });

  it('switches off every lit room and the lit lamps no room owns, reading the bridge once', async () => {
    bridgeIs(lit());
    const { user } = screenOf();

    await user.click(await allOff());

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls.map(call => call.slice(0, 2))).toEqual([
      ['/workbench/lights/room', { room_id: 'r1', on: false }],
      ['/workbench/lights/light', { light_id: 'porch', on: false }],
    ]);
    await waitFor(() => expect(bridgeReads()).toBe(2));
  });

  it('says what stayed on', async () => {
    bridgeIs(lit());
    api.post.mockRejectedValueOnce(new Error('refused'));
    const { user } = screenOf();

    await user.click(await allOff());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.lights.all_off_partial')
    );
    expect(api.post).toHaveBeenCalledTimes(2);
  });

  /** Nothing lit: a room with its lamp, a room with none, a lamp no room owns. */
  const dark = (): WorkbenchLights => ({
    ...lit(),
    rooms: lit().rooms.map(room => ({ ...room, on: false })),
    lights: lit().lights.map(lamp => ({ ...lamp, on: false })),
  });
  const allOn = () => screen.findByRole('button', { name: 'workbench.lights.all_on' });

  it('lights what has lamps once nothing is lit', async () => {
    bridgeIs(dark());
    const { user } = screenOf();

    await user.click(await allOn());

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls.map(call => call.slice(0, 2))).toEqual([
      ['/workbench/lights/room', { room_id: 'r1', on: true }],
      ['/workbench/lights/light', { light_id: 'porch', on: true }],
    ]);
    await waitFor(() => expect(bridgeReads()).toBe(2));
  });

  it('says « all on » once everything went off, on the same button', async () => {
    bridgeIs(lit());
    api.post.mockImplementation(() => {
      bridgeIs(dark());
      return Promise.resolve({});
    });
    const { user } = screenOf();
    const button = await allOff();

    await user.click(button);

    expect(await allOn()).toBe(button);
    expect(button).toHaveFocus();
  });

  it('says what stayed off', async () => {
    bridgeIs(dark());
    api.post.mockRejectedValueOnce(new Error('refused'));
    const { user } = screenOf();

    await user.click(await allOn());

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('workbench.lights.all_on_partial')
    );
  });

  it('asks nothing of a lamp that does not answer, and is not held lit by it', async () => {
    const [sofa, porch] = dark().lights;
    bridgeIs({
      ...dark(),
      rooms: [],
      lights: [
        { ...(porch ?? sofa), id: 'silent', room_id: null, on: true, reachable: false },
        { ...(porch ?? sofa), id: 'porch', room_id: null, on: false },
      ],
    });
    const { user } = screenOf();

    await user.click(await allOn());

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0]?.[1]).toEqual({ light_id: 'porch', on: true });
  });

  it('asks nothing of a house with no lamp', async () => {
    bridgeIs({ ...dark(), rooms: dark().rooms.slice(1), lights: [] });
    const { user } = screenOf();

    await user.click(await allOn());

    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('LightsTool — a zone', () => {
  const ZONE: WorkbenchRoom = {
    id: 'z1',
    name: 'A corner',
    kind: 'zone',
    light_ids: ['sofa', 'hall'],
    on: true,
    supports_color: false,
    mirek_min: null,
    mirek_max: null,
  };
  const zoned: WorkbenchLights = { ...BRIDGE, rooms: [...BRIDGE.rooms, ZONE] };

  beforeEach(() => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : zoned)
    );
  });

  it('comes after the rooms, and says what it is', async () => {
    screenOf();

    const names = await screen.findAllByRole('switch', { name: 'workbench.lights.room_switch' });
    expect(names).toHaveLength(2);
    const links = screen.getAllByRole('link', { name: /Living room|A corner/ });
    expect(links[0]).toHaveTextContent('Living room');
    expect(links[1]).toHaveTextContent('A corner');
    expect(links[1]).toHaveTextContent('workbench.lights.zone');
    expect(links[0]).not.toHaveTextContent('workbench.lights.zone');
  });

  it('is told to the bridge as a zone', async () => {
    const { user } = screenOf();

    const switches = await screen.findAllByRole('switch', {
      name: 'workbench.lights.room_switch',
    });
    await user.click(switches[1] as HTMLElement);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/room',
        { room_id: 'z1', kind: 'zone', on: false },
        undefined
      )
    );
  });

  it('is left out of « all off »: its lamps go with their rooms', async () => {
    const { user } = screenOf();

    await user.click(await screen.findByRole('button', { name: 'workbench.lights.all_off' }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls.map(([, body]) => body.room_id)).toEqual(['r1']);
  });
});

describe('LightsTool — a lamp that does not answer', () => {
  const silent = (reachable: boolean | null): WorkbenchLights => ({
    ...BRIDGE,
    lights: BRIDGE.lights.map(lamp => (lamp.id === 'sofa' ? { ...lamp, reachable } : lamp)),
  });
  const bridgeIs = (bridge: WorkbenchLights) =>
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : bridge)
    );

  it('says so and offers nothing it could not do', async () => {
    bridgeIs(silent(false));
    screenOf();

    const card = await screen.findByRole('group', { name: 'Sofa' });
    expect(within(card).getByText('workbench.lights.light_unreachable')).toBeVisible();
    expect(within(card).getByRole('switch')).toBeDisabled();
    expect(within(card).queryByRole('slider')).toBeNull();
  });

  it('greys its name, the one thing on its card that says so at a glance', async () => {
    bridgeIs(silent(false));
    screenOf();

    const card = await screen.findByRole('group', { name: 'Sofa' });
    expect(within(card).getByText('Sofa')).toHaveClass('text-muted-foreground');
  });

  it('keeps the name of a lamp that answers in the text colour', async () => {
    bridgeIs(silent(true));
    screenOf();

    const card = await screen.findByRole('group', { name: 'Sofa' });
    expect(within(card).getByText('Sofa')).toHaveClass('text-foreground');
  });

  it.each([true, null])('says nothing of a lamp reported as %s', async reachable => {
    bridgeIs(silent(reachable));
    screenOf();

    const card = await screen.findByRole('group', { name: 'Sofa' });
    expect(within(card).queryByText('workbench.lights.light_unreachable')).toBeNull();
    expect(within(card).getByRole('switch')).toBeEnabled();
  });
});

describe('LightsTool — lamps set apart by whether they answer', () => {
  const lamps = (...silent: string[]): WorkbenchLights => ({
    ...BRIDGE,
    lights: BRIDGE.lights.map(lamp => ({ ...lamp, reachable: !silent.includes(lamp.id) })),
  });
  const bridgeIs = (bridge: WorkbenchLights) =>
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : bridge)
    );

  it('draws those that answer first, then those that do not, each under its title', async () => {
    bridgeIs(lamps('sofa'));
    screenOf();

    await screen.findByRole('group', { name: 'Sofa' });
    const answering = screen.getByRole('region', { name: 'workbench.lights.answering_group' });
    const silent = screen.getByRole('region', { name: 'workbench.lights.silent_group' });
    expect(within(silent).getByRole('group', { name: 'Sofa' })).toBeVisible();
    expect(within(answering).queryByRole('group', { name: 'Sofa' })).toBeNull();
    expect(answering.compareDocumentPosition(silent)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('draws no title while every lamp answers', async () => {
    bridgeIs(lamps());
    screenOf();

    await screen.findByRole('group', { name: 'Sofa' });
    expect(screen.queryByRole('region', { name: 'workbench.lights.silent_group' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'workbench.lights.answering_group' })).toBeNull();
  });
});

describe('LightsTool — what is lit reads at a glance', () => {
  const lit = (on: boolean, reachable: boolean | null = true): WorkbenchLights => ({
    ...BRIDGE,
    rooms: BRIDGE.rooms.map(room => ({ ...room, on })),
    lights: BRIDGE.lights.map(lamp => ({ ...lamp, on, reachable })),
  });
  const bridgeIs = (bridge: WorkbenchLights) =>
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : bridge)
    );
  const roomCardOf = (link: HTMLElement) => link.closest('[data-lit]');

  it('marks a room that is on and a lamp that is on', async () => {
    bridgeIs(lit(true));
    screenOf();

    const lamp = await screen.findByRole('group', { name: 'Sofa' });
    const room = screen.getByRole('link', { name: /Living room/ });
    expect(lamp).toHaveAttribute('data-lit', 'true');
    expect(roomCardOf(room)).toHaveAttribute('data-lit', 'true');
  });

  it('tells what is off from what is lit', async () => {
    bridgeIs(lit(false));
    screenOf();

    const lamp = await screen.findByRole('group', { name: 'Sofa' });
    const room = screen.getByRole('link', { name: /Living room/ });
    expect(lamp).toHaveAttribute('data-lit', 'false');
    expect(roomCardOf(room)).toHaveAttribute('data-lit', 'false');
  });

  it('never marks a lamp that does not answer: nobody knows it is lit', async () => {
    bridgeIs(lit(true, false));
    screenOf();

    expect(await screen.findByRole('group', { name: 'Sofa' })).toHaveAttribute('data-lit', 'false');
  });
});

describe("LightsTool — a room's tone", () => {
  const toned: WorkbenchLights = {
    ...BRIDGE,
    rooms: [{ ...BRIDGE.rooms[0]!, supports_color: true, mirek_min: 200, mirek_max: 454 }],
  };
  const roomCard = () => screen.findByRole('link', { name: /Living room/ });
  const tone = async () => {
    const link = await roomCard();
    const card = link.closest('[aria-current]') ?? link.parentElement?.parentElement;
    return within(card as HTMLElement);
  };

  beforeEach(() => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : toned)
    );
  });

  it('folds what all its lamps accept, in their range', async () => {
    const { user } = screenOf();

    const card = await tone();
    await user.click(card.getByText('workbench.lights.customize'));

    const slider = card.getByRole('slider', { name: 'workbench.lights.temperature' });
    expect(slider).toHaveAttribute('min', '200');
    expect(slider).toHaveAttribute('max', '454');
    expect(card.getByLabelText('workbench.lights.colour')).toBeInTheDocument();
  });

  it('sends a temperature when the slider is released', async () => {
    const { user } = screenOf();

    const card = await tone();
    await user.click(card.getByText('workbench.lights.customize'));
    const slider = card.getByRole('slider', { name: 'workbench.lights.temperature' });
    fireEvent.input(slider, { target: { value: '300' } });
    fireEvent.change(slider, { target: { value: '300' } });

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/room',
        { room_id: 'r1', kind: 'room', mirek: 300 },
        undefined
      )
    );
  });

  it('sends a colour when its panel closes', async () => {
    const { user } = screenOf();

    const card = await tone();
    await user.click(card.getByText('workbench.lights.customize'));
    const picker = card.getByLabelText<HTMLInputElement>('workbench.lights.colour');
    fireEvent.input(picker, { target: { value: '#00ff00' } });
    picker.dispatchEvent(new Event('change', { bubbles: true }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/room',
        { room_id: 'r1', kind: 'room', color_hex: '#00ff00' },
        undefined
      )
    );
  });

  it('offers none to a room whose lamps take neither', async () => {
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : BRIDGE)
    );
    screenOf();

    const card = await tone();
    expect(card.queryByText('workbench.lights.customize')).toBeNull();
  });
});

describe('LightsTool — a scene in motion', () => {
  const moving = (playing: boolean): WorkbenchLights => ({
    ...BRIDGE,
    scenes: [
      { id: 's1', name: 'Relax', room_id: 'r1', active: playing, dynamic: true, playing },
      { id: 's2', name: 'Read', room_id: 'r1', active: false, dynamic: false, playing: false },
    ],
  });
  const bridgeIs = (bridge: WorkbenchLights) =>
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : bridge)
    );
  const motion = () => screen.findByRole('button', { name: 'workbench.lights.scene_motion' });

  it('is offered where the palette can play, and only there', async () => {
    bridgeIs(moving(false));
    screenOf();

    await screen.findByRole('button', { name: 'Read' });
    expect(
      await screen.findAllByRole('button', { name: 'workbench.lights.scene_motion' })
    ).toHaveLength(1);
  });

  it('starts it, and the scene alone is shown as it stands', async () => {
    bridgeIs(moving(false));
    const { user } = screenOf();

    await user.click(await motion());
    await user.click(screen.getByRole('button', { name: 'Read' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls.map(([, body]) => body)).toEqual([
      { scene_id: 's1', play: true },
      { scene_id: 's2' },
    ]);
  });

  it('holds it still once it plays, and says it plays', async () => {
    bridgeIs(moving(true));
    const { user } = screenOf();

    const button = await motion();
    expect(button).toHaveAttribute('aria-pressed', 'true');
    await user.click(button);

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/scene',
        { scene_id: 's1', play: false },
        undefined
      )
    );
  });
});

describe('LightsTool — a room’s scenes on its card', () => {
  it('are in reach below lg, without opening the room', async () => {
    media.desktop = false;
    const { user } = screenOf();
    const card = (await screen.findByRole('link', { name: /Living room/ })).closest(
      'div.space-y-3'
    );
    if (!(card instanceof HTMLElement)) throw new Error('no card');

    await user.click(within(card).getByRole('button', { name: 'Relax' }));

    await waitFor(() =>
      expect(api.post.mock.calls[0].slice(0, 2)).toEqual([
        '/workbench/lights/scene',
        { scene_id: 's1' },
      ])
    );
  });

  it('stay in the room from lg, where it sits beside the list', async () => {
    screenOf();
    const card = (await screen.findByRole('link', { name: /Living room/ })).closest(
      'div.space-y-3'
    );
    if (!(card instanceof HTMLElement)) throw new Error('no card');

    expect(within(card).queryByRole('button', { name: 'Relax' })).toBeNull();
  });
});

describe('LightsTool', () => {
  it('draws each lamp with the controls it can take', async () => {
    const { user } = screenOf();
    await screen.findByRole('group', { name: 'Sofa' });

    const sofa = lampCard('Sofa');
    expect(within(sofa).getByRole('slider', { name: 'workbench.lights.brightness' })).toBeVisible();
    await user.click(within(sofa).getByText('workbench.lights.customize'));
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
    const summary = within(sofa).getByText('workbench.lights.customize').closest('summary');
    expect(summary).not.toBeNull();
    expect(within(summary as HTMLElement).getByText('workbench.lights.kelvin')).toBeVisible();
    expect(
      (summary as HTMLElement).querySelector('[data-tone-colour]')?.getAttribute('style')
    ).toContain('rgb(255, 59, 48)');

    await user.click(within(sofa).getByText('workbench.lights.customize'));
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
                { id: 'r2', name: 'Salon', light_ids: ['hall'], on: true, ...PLAIN_ROOM },
                { id: 'r1', name: 'Cuisine', light_ids: ['sofa', 'plug'], on: true, ...PLAIN_ROOM },
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
    await user.click(within(lampCard('Sofa')).getByText('workbench.lights.customize'));
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
        { room_id: 'r1', kind: 'room', on: false },
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

  it('reaches a scene no room or zone holds, without opening a room', async () => {
    const bridge: WorkbenchLights = {
      ...BRIDGE,
      scenes: [
        ...BRIDGE.scenes,
        { id: 'z1', name: 'Downstairs', room_id: 'zone-1', active: false, ...STILL },
        { id: 'z2', name: 'Whole home', room_id: null, active: true, ...STILL },
      ],
    };
    api.get.mockImplementation((path: string) =>
      Promise.resolve(path === '/workbench' ? rail() : bridge)
    );
    const { user } = screenOf();

    const elsewhere = await screen.findByRole('region', {
      name: 'workbench.lights.other_scenes',
    });
    expect(within(elsewhere).queryByRole('button', { name: 'Relax' })).toBeNull();
    expect(within(elsewhere).getByRole('button', { name: 'Whole home' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );

    await user.click(within(elsewhere).getByRole('button', { name: 'Downstairs' }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/workbench/lights/scene',
        { scene_id: 'z1' },
        undefined
      )
    );
  });

  it('draws no such place while every scene has its room', async () => {
    screenOf();
    await screen.findByRole('button', { name: 'Relax' });

    expect(screen.queryByRole('region', { name: 'workbench.lights.other_scenes' })).toBeNull();
  });

  it('re-reads the bridge when asked, and says so when it cannot', async () => {
    const { user } = screenOf();
    const refresh = await screen.findByRole('button', { name: 'workbench.states.refresh' });
    api.get.mockClear();

    await user.click(refresh);
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/workbench/lights', expect.anything())
    );

    api.get.mockRejectedValueOnce(new Error('down'));
    await user.click(refresh);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('workbench.lights.failed'));
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
