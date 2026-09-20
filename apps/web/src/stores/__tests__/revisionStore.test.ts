/**
 * A writer declares what it changed, a reader re-reads it: the revision of a
 * resource is a number that only grows, one per resource, read as a query
 * dependency by whoever follows it.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { bumpRevision, useResourceRevision, useRevisionStore } from '../revisionStore';

describe('revisionStore', () => {
  beforeEach(() => {
    useRevisionStore.setState({ revisions: { live_connectors: 0 } });
  });

  it('starts at zero and grows by one on every bump of that resource', () => {
    expect(useRevisionStore.getState().revisions.live_connectors).toBe(0);
    bumpRevision('live_connectors');
    bumpRevision('live_connectors');
    expect(useRevisionStore.getState().revisions.live_connectors).toBe(2);
  });

  it('re-renders a reader following the resource with the new revision', () => {
    const { result } = renderHook(() => useResourceRevision('live_connectors'));
    expect(result.current).toBe(0);
    act(() => bumpRevision('live_connectors'));
    expect(result.current).toBe(1);
  });
});
