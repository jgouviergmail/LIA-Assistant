'use client';

import { RelationsWorkspace } from '@/components/relations/RelationsWorkspace';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function RelationsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <RelationsWorkspace lng={lng} />;
}
