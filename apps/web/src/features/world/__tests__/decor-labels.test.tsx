import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import type { SceneTarget } from '../scene-interactions';
import { WorldPrototype } from '../WorldPrototype';
import { WORLD } from '../definition';

const state = vi.hoisted(() => ({ target: null as SceneTarget | null }));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/useMediaQuery', () => ({ useMediaQuery: () => false }));
vi.mock('../useWorldRuntime', () => ({
  useWorldRuntime: () => ({
    canvasRef: { current: null },
    snapshot: {
      player: WORLD.spawn,
      bip: WORLD.bipSpawn,
      zone: 'arrival',
      zoom: 1,
      following: true,
      bipFollowing: false,
      metrics: { fps: 0, frameP95: 0, renderP95: 0, sprites: 0, textureBytes: 0 },
      nearby: state.target,
      hover: state.target ? { target: state.target, point: { x: 200, y: 200 } } : null,
    },
    failed: false,
    command: vi.fn(),
    retry: vi.fn(),
    focusScene: vi.fn(),
  }),
}));
vi.mock('../WorldHud', () => ({
  WorldHud: ({ nearbyLabel }: ComponentProps<typeof import('../WorldHud').WorldHud>) => (
    <span data-testid="nearby">{nearbyLabel ?? 'PLACE'}</span>
  ),
}));
afterEach(cleanup);

it.each(['pond', 'lamp', 'display'] as const)(
  'keeps the %s clickable without announcing an action in the HUD or object tooltip',
  kind => {
    const prop = WORLD.props.find(item => item.kind === kind);
    if (!prop) throw new Error('Missing authored decor');
    state.target = { kind: 'object', id: prop.id };
    const label = vi.fn(() => 'ACTION');
    render(<WorldPrototype lng="en" ownerId="owner" sceneLabel={label} />);
    expect(screen.getByTestId('nearby')).toHaveTextContent('PLACE');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(label).not.toHaveBeenCalled();
  }
);
it('retains the functional object label in both the HUD and its tooltip', () => {
  const prop = WORLD.props.find(item => item.key === 'health');
  if (!prop) throw new Error('Missing Health feature');
  state.target = { kind: 'object', id: prop.id };
  render(<WorldPrototype lng="en" ownerId="owner" sceneLabel={() => 'HEALTH'} />);
  expect(screen.getByTestId('nearby')).toHaveTextContent('HEALTH');
  expect(screen.getByRole('tooltip')).toHaveTextContent('HEALTH');
});
