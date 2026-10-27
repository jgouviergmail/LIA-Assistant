import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSkillProposal, useSkillProposalActions } from '../useSkillProposal';
import type { SkillProposal } from '@/lib/skill-proposals/types';

const mocks = vi.hoisted(() => ({ auth: vi.fn(), get: vi.fn(), post: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: mocks.auth }));
vi.mock('@/lib/api-client', () => ({ default: { get: mocks.get, post: mocks.post } }));
const proposal: SkillProposal = {
  id: 'a'.repeat(32),
  name: 'private-skill',
  description: 'private metadata',
  status: 'pending',
  replaces: false,
  changes: null,
  expires_at: new Date(Date.now() + 60000).toISOString(),
  files: [{ path: 'SKILL.md', size: 20, content: 'private complete instructions' }],
};

beforeEach(() => {
  mocks.auth.mockReturnValue({ user: { id: 'owner' } });
  mocks.get.mockReset().mockResolvedValue(proposal);
  mocks.post.mockReset().mockResolvedValue(proposal);
});

describe('skill proposal account lifetime', () => {
  it('hides old private files before the next account response', async () => {
    const { result, rerender } = renderHook(() => useSkillProposal(proposal.id));
    await waitFor(() =>
      expect(result.current.data?.files[0].content).toBe('private complete instructions')
    );
    mocks.get.mockImplementation(() => new Promise(() => {}));
    mocks.auth.mockReturnValue({ user: { id: 'other' } });
    rerender();
    expect(result.current.data).toBeUndefined();
    await waitFor(() => {
      expect(mocks.get).toHaveBeenCalledTimes(2);
      expect(result.current.loading).toBe(true);
    });
  });

  it('refuses a retained old-account install callback', async () => {
    const { result, rerender } = renderHook(() => useSkillProposalActions());
    const retained = result.current.install;
    mocks.auth.mockReturnValue({ user: { id: 'other' } });
    rerender();
    await act(async () => {
      await expect(retained(proposal.id)).rejects.toThrow();
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
