import { Suspense } from 'react';
import { Metadata } from 'next';

import { DocumentViewerFromParams } from '@/components/documents/DocumentViewerFromParams';
import { LoadingSpinner } from '@/components/ui/loading-spinner';

export const metadata: Metadata = {
  title: 'Document - LIA',
};

interface DocumentPageProps {
  params: Promise<{ lng: string; id: string }>;
}

/**
 * HTML view of a generated document (ADR-226 amendment 2026-08-18).
 *
 * The Suspense boundary is load-bearing: the client component reads
 * `useSearchParams()` (filename + type travel from the card link), and a
 * page rendering it without Suspense passes every local gate but fails the
 * production `next build` prerender (v1.25.16 lesson).
 */
export default async function DocumentPage({ params }: DocumentPageProps) {
  const { id } = await params;

  return (
    <Suspense fallback={<LoadingSpinner />}>
      <DocumentViewerFromParams attachmentId={id} />
    </Suspense>
  );
}
