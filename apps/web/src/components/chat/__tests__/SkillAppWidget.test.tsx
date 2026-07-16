/**
 * SkillAppWidget — the registry-item gating (null unless a SKILL_APP item) and
 * the image-card rendering.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

const { useRegistryItem } = vi.hoisted(() => ({ useRegistryItem: vi.fn() }));
vi.mock('@/lib/registry-context', () => ({ useRegistryItem }));

import { SkillAppWidget } from '../SkillAppWidget';

beforeEach(() => vi.clearAllMocks());

describe('SkillAppWidget', () => {
  it('renders the unavailable placeholder when the registry item is missing', () => {
    useRegistryItem.mockReturnValue(undefined);
    renderWithProviders(<SkillAppWidget registryId="r1" />);
    expect(screen.getByText('skill_apps.error')).toBeInTheDocument();
  });

  it('renders the unavailable placeholder when the item is not a SKILL_APP', () => {
    useRegistryItem.mockReturnValue({ type: 'MCP_APP', payload: {} });
    renderWithProviders(<SkillAppWidget registryId="r1" />);
    expect(screen.getByText('skill_apps.error')).toBeInTheDocument();
  });

  it('renders the image card for a SKILL_APP item with an image', () => {
    useRegistryItem.mockReturnValue({
      type: 'SKILL_APP',
      payload: { image_url: 'https://x/y.png', image_alt: 'A chart' },
    });
    renderWithProviders(<SkillAppWidget registryId="r1" />);
    expect(screen.getByRole('img', { name: 'A chart' })).toHaveAttribute('src', 'https://x/y.png');
  });
});
