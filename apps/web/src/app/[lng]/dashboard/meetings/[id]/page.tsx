'use client';
import { use } from 'react';
import { MeetingDetailWorkspace } from '@/components/meetings/MeetingDetailWorkspace';
import { useLanguageParam } from '@/hooks/useLanguageParam';
export default function MeetingPage({ params }: { params: Promise<{ lng: string; id: string }> }) {
  const { id } = use(params);
  const lng = useLanguageParam(params);
  return <MeetingDetailWorkspace lng={lng} id={id} />;
}
