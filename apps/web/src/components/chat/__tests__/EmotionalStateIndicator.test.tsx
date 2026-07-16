/**
 * EmotionalStateIndicator — the icon/badge/full variants, the tooltip toggle,
 * and the useEmotionalState hook (SSE-driven state + memory count).
 */

import { describe, it, expect } from 'vitest';

import { renderWithProviders, renderHook, screen, act } from '@/__tests__/test-utils';
import { EmotionalStateIndicator, useEmotionalState } from '../EmotionalStateIndicator';

describe('EmotionalStateIndicator — variants', () => {
  it('renders the icon variant as an image labelled by the state', () => {
    renderWithProviders(<EmotionalStateIndicator state="neutral" variant="icon" />);
    expect(screen.getByRole('img', { name: 'Mode factuel' })).toBeInTheDocument();
  });

  it('omits the tooltip title when showTooltip is false', () => {
    renderWithProviders(
      <EmotionalStateIndicator state="neutral" variant="icon" showTooltip={false} />
    );
    expect(screen.getByRole('img', { name: 'Mode factuel' })).not.toHaveAttribute('title');
  });

  it('renders the label text in the badge variant', () => {
    renderWithProviders(<EmotionalStateIndicator state="comfort" variant="badge" />);
    expect(screen.getByText('Terrain positif')).toBeInTheDocument();
  });

  it('renders the label and description in the full variant', () => {
    renderWithProviders(<EmotionalStateIndicator state="danger" variant="full" />);
    expect(screen.getByText('Zone sensible')).toBeInTheDocument();
  });
});

describe('useEmotionalState', () => {
  it('starts neutral with no memories', () => {
    const { result } = renderHook(() => useEmotionalState());
    expect(result.current.state).toBe('neutral');
    expect(result.current.memoryCount).toBe(0);
    expect(result.current.hasMemories).toBe(false);
  });

  it('updates state and memory count from a response', () => {
    const { result } = renderHook(() => useEmotionalState());
    act(() => {
      result.current.updateFromResponse({ emotional_state: 'comfort', memory_count: 3 });
    });
    expect(result.current.state).toBe('comfort');
    expect(result.current.memoryCount).toBe(3);
    expect(result.current.hasMemories).toBe(true);
  });

  it('ignores missing fields in the response', () => {
    const { result } = renderHook(() => useEmotionalState('danger'));
    act(() => {
      result.current.updateFromResponse({});
    });
    expect(result.current.state).toBe('danger');
    expect(result.current.memoryCount).toBe(0);
  });

  it('resets back to neutral with no memories', () => {
    const { result } = renderHook(() => useEmotionalState('comfort'));
    act(() => {
      result.current.updateFromResponse({ emotional_state: 'danger', memory_count: 5 });
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.state).toBe('neutral');
    expect(result.current.memoryCount).toBe(0);
    expect(result.current.hasMemories).toBe(false);
  });
});
