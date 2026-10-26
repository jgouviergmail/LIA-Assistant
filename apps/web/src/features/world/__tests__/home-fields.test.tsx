import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorldHomeFields } from '../WorldHomeFields';
import { HOME_PALETTES } from '../home-catalogue';
import type { HomeEdit } from '../home-protocol';

vi.mock('@/i18n/client', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const value: HomeEdit = {
  palette: 'auto',
};
describe('home palette controls', () => {
  it('offers named palettes and emits only the selected colour', () => {
    const onChange = vi.fn();
    render(<WorldHomeFields lng="en" value={value} onChange={onChange} />);
    for (const palette of HOME_PALETTES)
      expect(screen.getByRole('radio', { name: 'world.home.palettes.' + palette })).toBeEnabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'world.home.palettes.teal' }));
    expect(onChange).toHaveBeenCalledWith({ palette: 'teal' });
  });

  it('disables palette changes while recovering unreadable preferences', () => {
    render(<WorldHomeFields lng="en" value={value} onChange={vi.fn()} disabled />);
    for (const control of screen.getAllByRole('radio')) expect(control).toBeDisabled();
  });
});
