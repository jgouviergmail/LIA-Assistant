/**
 * The holder list (ADR-276, D77, D79): me, LIA, then every peer — each
 * wearing the badge's glyph, LIA's spark in the accent — and the choice
 * reported as `assignPatch` reads it.
 */
import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import { HolderSelect } from '@/components/workboard/HolderSelect';

const PEERS = [
  { peer_id: 'p1', peer_display_name: 'Marie' },
  { peer_id: 'p2', peer_display_name: 'Ahmed' },
];

describe('HolderSelect', () => {
  it('offers me, LIA and every peer, each wearing its glyph', async () => {
    const { user } = renderWithProviders(
      <HolderSelect value="me" label="Holder" peers={PEERS} onChange={vi.fn()} />
    );

    expect(screen.getByRole('combobox', { name: 'Holder' })).toHaveTextContent(
      'workboard.party.me'
    );
    await user.click(screen.getByRole('combobox', { name: 'Holder' }));
    const options = await screen.findAllByRole('option');
    expect(options.map(option => option.textContent)).toEqual([
      'workboard.party.me',
      'workboard.party.lia',
      'Marie',
      'Ahmed',
    ]);
    // Every person in the theme colour, LIA and humans alike (D82).
    expect(options[0].querySelector('.lucide-user')?.classList).toContain('text-primary');
    expect(options[1].querySelector('.lucide-sparkles')?.classList).toContain('text-primary');
    expect(options[2].querySelector('.lucide-users')?.classList).toContain('text-primary');
  });

  it('still names a holder whose connections have not loaded yet', async () => {
    // The card's badge already resolves an unresolvable id to « somebody
    // else » rather than to a blank (`assigneeParty`). The list beside it
    // showed an EMPTY trigger for the same ticket, while the peers were in
    // flight or a connection had just gone.
    const { user } = renderWithProviders(
      <HolderSelect value="p-unknown" label="Holder" peers={[]} onChange={vi.fn()} />
    );

    const trigger = screen.getByRole('combobox', { name: 'Holder' });
    expect(trigger).toHaveTextContent('workboard.party.unknown');
    await user.click(trigger);
    const options = await screen.findAllByRole('option');
    // Offered LAST, and only because it is the current value: it is not a
    // holder anybody can choose.
    expect(options.map(option => option.textContent)).toEqual([
      'workboard.party.me',
      'workboard.party.lia',
      'workboard.party.unknown',
    ]);
    // Shown, never takeable: it is the value already in force, and choosing
    // it would send the server an id it cannot accept.
    expect(options[2]).toHaveAttribute('aria-disabled', 'true');
  });

  it('adds nothing when the current holder is one of the offered ones', async () => {
    const { user } = renderWithProviders(
      <HolderSelect value="p1" label="Holder" peers={PEERS} onChange={vi.fn()} />
    );

    await user.click(screen.getByRole('combobox', { name: 'Holder' }));
    expect(await screen.findAllByRole('option')).toHaveLength(4);
  });

  it('reports a peer by id', async () => {
    const onChange = vi.fn();
    const { user } = renderWithProviders(
      <HolderSelect value="me" label="Holder" peers={PEERS} onChange={onChange} />
    );

    await user.click(screen.getByRole('combobox', { name: 'Holder' }));
    await user.click(await screen.findByRole('option', { name: 'Ahmed' }));

    expect(onChange).toHaveBeenCalledWith('p2');
  });

  it('shows the label when asked, and names the control by it', () => {
    renderWithProviders(
      <HolderSelect
        id="holder"
        hideLabel={false}
        value="lia"
        label="Holder"
        peers={[]}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('Holder').tagName).toBe('LABEL');
    const trigger = screen.getByRole('combobox', { name: 'Holder' });
    expect(trigger).toHaveTextContent('workboard.party.lia');
    expect(trigger.querySelector('.lucide-sparkles')).not.toBeNull();
  });
});
