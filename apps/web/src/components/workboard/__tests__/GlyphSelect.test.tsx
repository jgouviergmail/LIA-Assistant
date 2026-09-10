/**
 * The list behind the column and the holder lists (ADR-276, D79): a glyph,
 * then a word, on every item — and the three mechanics both vocabularies
 * share: the two label modes, the mirrored trigger, and the containment of a
 * press, a key and a gesture.
 */
import { describe, it, expect, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';
import { GlyphSelect, type GlyphSelectProps } from '@/components/workboard/GlyphSelect';

const ITEMS = [
  { value: 'a', glyph: <svg data-testid="glyph-a" aria-hidden="true" />, text: 'Alpha' },
  { value: 'b', glyph: <svg data-testid="glyph-b" aria-hidden="true" />, text: 'Beta' },
] as const;

function render(overrides: Partial<GlyphSelectProps> = {}) {
  const props: GlyphSelectProps = {
    value: 'a',
    label: 'Pick',
    items: ITEMS,
    onChange: vi.fn(),
    ...overrides,
  };
  return { ...renderWithProviders(<GlyphSelect {...props} />), props };
}

describe('GlyphSelect', () => {
  it('is named by its label, hidden by default and visible on request', () => {
    const hidden = render();
    expect(screen.getByRole('combobox', { name: 'Pick' })).toHaveAttribute('aria-label', 'Pick');
    expect(screen.queryByText('Pick')).toBeNull();
    hidden.unmount();

    render({ hideLabel: false, id: 'pick' });
    const trigger = screen.getByRole('combobox', { name: 'Pick' });
    expect(trigger).not.toHaveAttribute('aria-label');
    expect(trigger).toHaveAttribute('id', 'pick');
    expect(screen.getByText('Pick').tagName).toBe('LABEL');
  });

  it('draws the family glyph in the visible label when given one', () => {
    render({
      hideLabel: false,
      id: 'pick',
      labelGlyph: <svg data-testid="family" aria-hidden="true" />,
    });

    const label = screen.getByText('Pick');
    expect(label.tagName).toBe('LABEL');
    expect(label.contains(screen.getByTestId('family'))).toBe(true);
    expect(label.className).toContain('flex');
  });

  it('mirrors the chosen item on the closed trigger, glyph first', () => {
    render({ value: 'b' });

    const trigger = screen.getByRole('combobox', { name: 'Pick' });
    expect(trigger).toHaveTextContent('Beta');
    const glyph = screen.getByTestId('glyph-b');
    expect(trigger.contains(glyph)).toBe(true);
    expect(glyph.parentElement?.firstElementChild).toBe(glyph);
  });

  it('offers every item as an option wearing its glyph before its word', async () => {
    const { user } = render();

    await user.click(screen.getByRole('combobox', { name: 'Pick' }));
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual(['Alpha', 'Beta']);
    const glyph = screen.getAllByTestId('glyph-b').at(-1);
    expect(screen.getByRole('option', { name: 'Beta' }).contains(glyph ?? null)).toBe(true);
    expect(glyph?.parentElement?.firstElementChild).toBe(glyph);
  });

  it('reports the chosen value', async () => {
    const { user, props } = render();

    await user.click(screen.getByRole('combobox', { name: 'Pick' }));
    await user.click(await screen.findByRole('option', { name: 'Beta' }));

    expect(props.onChange).toHaveBeenCalledWith('b');
  });

  it('keeps a press and a key on the trigger from any ancestor, and still opens', async () => {
    // Born on a card that can be a sortable item: a drag listener above must
    // never see the press. Radix composes its own handlers after ours.
    const pointer = vi.fn();
    const key = vi.fn();
    const { user } = renderWithProviders(
      <div role="group" aria-label="harness" onPointerDown={pointer} onKeyDown={key}>
        <GlyphSelect value="a" label="Pick" items={ITEMS} onChange={vi.fn()} />
      </div>
    );

    const trigger = screen.getByRole('combobox', { name: 'Pick' });
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    expect(pointer).not.toHaveBeenCalled();
    expect(key).not.toHaveBeenCalled();
    // …and those very events still opened the list: Radix's handlers ran
    // after ours. A second click here would land on the `pointer-events:
    // none` an open list paints over the page.
    expect(await screen.findAllByRole('option')).toHaveLength(2);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('option')).toBeNull();
  });

  it('keeps a gesture started inside the open list to the list', async () => {
    // The React tree runs through the portal: without this a swipe across an
    // item reaches the board's column swipe underneath.
    const touch = vi.fn();
    const { user } = renderWithProviders(
      <div role="group" aria-label="harness" onTouchStart={touch} onTouchEnd={touch}>
        <GlyphSelect value="a" label="Pick" items={ITEMS} onChange={vi.fn()} />
      </div>
    );

    await user.click(screen.getByRole('combobox', { name: 'Pick' }));
    const option = await screen.findByRole('option', { name: 'Beta' });
    fireEvent.touchStart(option, { touches: [{ clientX: 300, clientY: 200 }] });
    fireEvent.touchEnd(option, { changedTouches: [{ clientX: 100, clientY: 200 }] });

    expect(touch).not.toHaveBeenCalled();
  });

  it('can be disabled', () => {
    render({ disabled: true });

    expect(screen.getByRole('combobox', { name: 'Pick' })).toBeDisabled();
  });
});
