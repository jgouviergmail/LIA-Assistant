/**
 * Tests for RAG Spaces hooks: useSpaces, useSpaceDetail, useActiveSpaces.
 *
 * Strategy: mock useApiQuery and useApiMutation at module level, then verify
 * that the hooks expose the correct derived state and that mutation callbacks
 * apply optimistic updates via setData.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { RAGSpace, RAGSpaceListResponse } from '@/types/rag-spaces';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockSetData = vi.fn();
const mockRefetch = vi.fn();
const mockMutate = vi.fn();

vi.mock('@/hooks/useApiQuery', () => ({
  useApiQuery: vi.fn(),
}));

vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: vi.fn(() => ({
    mutate: mockMutate,
    loading: false,
    error: null,
    reset: vi.fn(),
    data: null,
  })),
}));

// Import after mocks are declared
import { useApiQuery } from '@/hooks/useApiQuery';
import { useSpaces, useSpaceDetail, useActiveSpaces } from '../useSpaces';

const mockedUseApiQuery = vi.mocked(useApiQuery);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SPACE_A: RAGSpace = {
  id: 'space-1',
  name: 'Work',
  description: 'Work documents',
  is_active: true,
  document_count: 3,
  ready_document_count: 3,
  total_size: 1024,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const SPACE_B: RAGSpace = {
  id: 'space-2',
  name: 'Personal',
  description: null,
  is_active: false,
  document_count: 1,
  ready_document_count: 0,
  total_size: 512,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
};

const LIST_RESPONSE: RAGSpaceListResponse = {
  spaces: [SPACE_A, SPACE_B],
  total: 2,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupQueryMock(data: RAGSpaceListResponse = LIST_RESPONSE) {
  mockedUseApiQuery.mockReturnValue({
    data,
    loading: false,
    error: null,
    refetch: mockRefetch,
    setData: mockSetData,
  } as ReturnType<typeof useApiQuery>);
}

// ---------------------------------------------------------------------------
// useSpaces
// ---------------------------------------------------------------------------

describe('useSpaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupQueryMock();
  });

  it('returns spaces list with derived counts', () => {
    const { result } = renderHook(() => useSpaces());

    expect(result.current.spaces).toHaveLength(2);
    expect(result.current.total).toBe(2);
    expect(result.current.activeCount).toBe(1); // only SPACE_A is active
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('createSpace calls mutate and applies optimistic update via setData', async () => {
    const newSpace = { id: 'space-3', name: 'New', description: null, is_active: true };
    mockMutate.mockResolvedValueOnce(newSpace);

    const { result } = renderHook(() => useSpaces());

    await act(async () => {
      await result.current.createSpace({ name: 'New' });
    });

    expect(mockMutate).toHaveBeenCalledWith('/rag-spaces', { name: 'New' });
    // setData should have been called with an updater function
    expect(mockSetData).toHaveBeenCalledTimes(1);
    const updater = mockSetData.mock.calls[0][0];
    expect(typeof updater).toBe('function');

    // Verify the updater adds the new space
    const updated = updater(LIST_RESPONSE);
    expect(updated.spaces).toHaveLength(3);
    expect(updated.total).toBe(3);
    expect(updated.spaces[2].name).toBe('New');
  });

  it('deleteSpace removes space from list via setData', async () => {
    mockMutate.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useSpaces());

    await act(async () => {
      await result.current.deleteSpace('space-1');
    });

    expect(mockMutate).toHaveBeenCalledWith('/rag-spaces/space-1');
    const updater = mockSetData.mock.calls[0][0];
    const updated = updater(LIST_RESPONSE);
    expect(updated.spaces).toHaveLength(1);
    expect(updated.spaces[0].id).toBe('space-2');
    expect(updated.total).toBe(1);
  });

  it('toggleSpace updates is_active flag via setData', async () => {
    mockMutate.mockResolvedValueOnce({ id: 'space-2', is_active: true });

    const { result } = renderHook(() => useSpaces());

    await act(async () => {
      await result.current.toggleSpace('space-2');
    });

    expect(mockMutate).toHaveBeenCalledWith('/rag-spaces/space-2/toggle');
    const updater = mockSetData.mock.calls[0][0];
    const updated = updater(LIST_RESPONSE);
    const toggled = updated.spaces.find((s: RAGSpace) => s.id === 'space-2');
    expect(toggled?.is_active).toBe(true);
  });

  it('updateSpace patches name and description via setData', async () => {
    mockMutate.mockResolvedValueOnce({
      id: 'space-1',
      name: 'Renamed',
      description: 'Updated desc',
    });

    const { result } = renderHook(() => useSpaces());

    await act(async () => {
      await result.current.updateSpace('space-1', {
        name: 'Renamed',
        description: 'Updated desc',
      });
    });

    expect(mockMutate).toHaveBeenCalledWith('/rag-spaces/space-1', {
      name: 'Renamed',
      description: 'Updated desc',
    });
    const updater = mockSetData.mock.calls[0][0];
    const updated = updater(LIST_RESPONSE);
    const patched = updated.spaces.find((s: RAGSpace) => s.id === 'space-1');
    expect(patched?.name).toBe('Renamed');
    expect(patched?.description).toBe('Updated desc');
  });
});

// ---------------------------------------------------------------------------
// useSpaceDetail
// ---------------------------------------------------------------------------

describe('useSpaceDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns space detail when spaceId is provided', () => {
    const detail = { ...SPACE_A, documents: [] };
    mockedUseApiQuery.mockReturnValue({
      data: detail,
      loading: false,
      error: null,
      refetch: mockRefetch,
      setData: mockSetData,
    } as ReturnType<typeof useApiQuery>);

    const { result } = renderHook(() => useSpaceDetail('space-1'));

    expect(result.current.space).toEqual(detail);
    expect(result.current.loading).toBe(false);
    expect(mockedUseApiQuery).toHaveBeenCalledWith(
      '/rag-spaces/space-1',
      expect.objectContaining({ enabled: true })
    );
  });

  it('disables query when spaceId is null', () => {
    mockedUseApiQuery.mockReturnValue({
      data: undefined,
      loading: false,
      error: null,
      refetch: mockRefetch,
      setData: mockSetData,
    } as ReturnType<typeof useApiQuery>);

    const { result } = renderHook(() => useSpaceDetail(null));

    expect(result.current.space).toBeNull();
    expect(mockedUseApiQuery).toHaveBeenCalledWith(
      '',
      expect.objectContaining({ enabled: false })
    );
  });
});

// ---------------------------------------------------------------------------
// useActiveSpaces
// ---------------------------------------------------------------------------

describe('useActiveSpaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns only active spaces with count', () => {
    setupQueryMock();

    const { result } = renderHook(() => useActiveSpaces());

    expect(result.current.activeSpaces).toHaveLength(1);
    expect(result.current.activeSpaces[0].id).toBe('space-1');
    expect(result.current.activeCount).toBe(1);
    expect(result.current.loading).toBe(false);
  });
});
