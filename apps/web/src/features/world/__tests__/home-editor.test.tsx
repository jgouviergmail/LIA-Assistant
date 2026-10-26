import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import { WorldHomeControls } from '../WorldHomeControls';
import type { HomeView } from '../home-protocol';
import { cloneElement, type ComponentProps } from 'react';
import type { WorldHomeFields } from '../WorldHomeFields';
import type { HomeEdit } from '../home-protocol';

// Radix portal layout is qualified in the real native browser journey. This
// controller port exercises edit/save lifetimes without emulating browser layout.
type FieldProps = ComponentProps<typeof WorldHomeFields>;
const field = vi.hoisted(() => {
  const state: { props?: FieldProps } = {};
  return state;
});
vi.mock('../WorldHomeFields', () => ({
  WorldHomeFields: (props: FieldProps) => {
    field.props = props;
    return null;
  },
}));

const port = vi.hoisted(() => ({
  save: vi.fn(),
  refresh: vi.fn(),
  value: null as HomeView | null,
  saving: false,
}));
vi.mock('../useWorldHome', () => ({
  useWorldHome: () => ({
    home: port.value,
    save: port.save,
    refresh: port.refresh,
    loading: false,
    saving: port.saving,
    failed: false,
  }),
}));
vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const owner = '11111111-1111-4111-8111-111111111111';
function homeFixture(): HomeView {
  return {
    owner_id: owner,
    needs_reset: false,
    preferences: { version: 1, revision: 0, palette: 'auto' },
    decoration: {
      automatic_palette: 'clay',
      palette: 'clay',
    },
  };
}
beforeEach(() => {
  port.value = homeFixture();
  port.saving = false;
  port.save.mockReset();
  port.refresh.mockReset();
});
function edit(palette: HomeEdit['palette']) {
  const current = field.props;
  if (!current) throw new Error('Missing edit port');
  act(() => current.onChange({ ...current.value, palette }));
}
function setup() {
  const skin = vi.fn();
  const editing = vi.fn();
  const element = (
    <WorldHomeControls lng="en" ownerId={owner} enabled onSkin={skin} onEditing={editing} />
  );
  const result = render(element);
  fireEvent.click(screen.getByRole('button', { name: 'world.home.open' }));
  return { ...result, element, skin, editing };
}

describe('private home editor transactions', () => {
  it('keeps save focused and rejects another submission while saving', () => {
    const { rerender, element } = setup();
    const save = screen.getByRole('button', { name: 'world.home.save' });
    save.focus();
    port.saving = true;
    rerender(cloneElement(element));
    expect(save).toHaveFocus();
    expect(save).not.toBeDisabled();
    expect(save).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(save);
    expect(port.save).not.toHaveBeenCalled();
  });
  it('previews locally and cancels without a write', async () => {
    const { skin } = setup();
    edit('sage');
    await waitFor(() =>
      expect(skin).toHaveBeenLastCalledWith(
        expect.objectContaining({
          palette: 'sage',
        })
      )
    );
    fireEvent.click(screen.getByRole('button', { name: 'world.home.cancel' }));
    expect(port.save).not.toHaveBeenCalled();
    await waitFor(() => expect(skin).toHaveBeenLastCalledWith(port.value?.decoration));
  });
  it('preserves the draft and original revision when settings change elsewhere', async () => {
    const { rerender, element } = setup();
    edit('sage');
    const fresh = homeFixture();
    fresh.preferences.revision = 2;
    fresh.preferences.palette = 'amber';
    port.value = fresh;
    rerender(cloneElement(element));
    expect(field.props?.value.palette).toBe('sage');
    port.save.mockRejectedValueOnce(new ApiError('conflict', 409));
    fireEvent.click(screen.getByRole('button', { name: 'world.home.save' }));
    await screen.findByText('world.home.conflict');
    expect(field.props?.value.palette).toBe('sage');
    expect(port.save).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_revision: 0,
        palette: 'sage',
      })
    );
  });
  it('does not close a newer editing session when an older save finishes', async () => {
    setup();
    let finish!: (accepted: boolean) => void;
    port.save.mockReturnValueOnce(
      new Promise<boolean>(resolve => {
        finish = resolve;
      })
    );
    fireEvent.click(screen.getByRole('button', { name: 'world.home.save' }));
    fireEvent.click(screen.getByRole('button', { name: 'world.home.cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'world.home.open' }));
    edit('teal');
    await act(async () => finish(true));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(field.props?.value.palette).toBe('teal');
  });
  it('requires an explicit reset/save before replacing unreadable preferences', async () => {
    const value = homeFixture();
    value.needs_reset = true;
    port.value = value;
    setup();
    expect(screen.getByRole('button', { name: 'world.home.save' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'world.home.reset' }));
    expect(port.save).not.toHaveBeenCalled();
    port.save.mockResolvedValueOnce(true);
    fireEvent.click(screen.getByRole('button', { name: 'world.home.save' }));
    await waitFor(() =>
      expect(port.save).toHaveBeenCalledWith({ expected_revision: 0, reset: true })
    );
  });
});

afterEach(() => vi.restoreAllMocks());

it('returns to visible world controls when resizing folds the home editor opener', async () => {
  render(
    <section>
      <div className="world-prototype">
        <button className="world-hud-toggle">World controls</button>
      </div>
      <div className="world-session-strip">
        <WorldHomeControls lng="en" ownerId={owner} enabled onSkin={vi.fn()} onEditing={vi.fn()} />
      </div>
    </section>
  );
  const opener = screen.getByRole('button', { name: 'world.home.open' });
  fireEvent.click(opener);
  await screen.findByRole('dialog');
  // Browsers refuse to focus the folded toolbar after a responsive resize.
  vi.spyOn(opener, 'focus').mockImplementation(() => {});
  fireEvent.click(screen.getByRole('button', { name: 'world.home.cancel' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'World controls' })).toHaveFocus());
});
