import { applicationStateChangeSchema } from '@/types/application-state';
import type { SSEHandler } from './types';

export const handleApplicationStateChanged: SSEHandler = (chunk, context) => {
  const metadata = chunk.metadata;
  if (!metadata || !('change' in metadata)) return;
  const parsed = applicationStateChangeSchema.safeParse(metadata.change);
  if (!parsed.success) return;
  // Replayed invalidations reread current state; they never replay a mutation.
  context.handleApplicationStateChange?.(parsed.data);
};
