import { qualifiedCollectionSchema } from '@/types/result-preview';
import type { SSEHandler } from './types';

export const handleResultPreview: SSEHandler = (chunk, context) => {
  const metadata = chunk.metadata;
  if (!metadata || !('collection' in metadata)) return;
  const result = qualifiedCollectionSchema.safeParse(metadata.collection);
  if (!result.success) return;
  context.dispatch({
    type: 'RESULT_PREVIEW',
    payload: {
      messageId: context.progressMessageId ?? context.assistantMessageId,
      collection: result.data,
    },
  });
};
