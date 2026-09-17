/**
 * useSourceActions — a refusal that names itself is told in its own words.
 *
 * Linking a Drive folder inside (or above) an already linked tree is refused
 * with a coded 409; the toast must carry that reason, not the generic
 * « failed to link ». An uncoded failure keeps the generic wording.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { ApiError } from '@/lib/api-client';

const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

import { useSourceActions } from '../useSourceActions';

const refetch = vi.fn();

function hook(link: (id: string, name: string) => Promise<unknown>) {
  return renderHook(() =>
    useSourceActions<{ id: string; folder_name: string }>({
      sources: [],
      namespace: 'spaces.drive',
      nameOf: source => source.folder_name,
      link,
      unlink: vi.fn(),
      sync: vi.fn(),
      refetch,
      linkErrorKeys: { drive_folder_nested: 'spaces.drive.link_nested' },
    })
  );
}

beforeEach(() => {
  toast.error.mockReset();
  toast.success.mockReset();
  refetch.mockReset();
});

describe('useSourceActions — link refusals', () => {
  it('tells a coded refusal in its own words', async () => {
    const link = vi.fn().mockRejectedValue(
      new ApiError('conflict', 409, { detail: { code: 'drive_folder_nested' } })
    );
    const { result } = hook(link);
    await act(() => result.current.handleLink('child', 'Child'));
    expect(toast.error).toHaveBeenCalledWith('spaces.drive.link_nested');
    expect(refetch).not.toHaveBeenCalled();
  });

  it('keeps the generic wording for an uncoded failure', async () => {
    const link = vi.fn().mockRejectedValue(new ApiError('boom', 500, { detail: 'boom' }));
    const { result } = hook(link);
    await act(() => result.current.handleLink('x', 'X'));
    expect(toast.error).toHaveBeenCalledWith('spaces.drive.link_error');
  });
});
