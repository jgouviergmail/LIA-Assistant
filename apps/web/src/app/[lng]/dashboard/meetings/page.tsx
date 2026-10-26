'use client';
import { MeetingsWorkspace } from '@/components/meetings/MeetingsWorkspace';
import { useLanguageParam } from '@/hooks/useLanguageParam';
export default function MeetingsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <MeetingsWorkspace lng={lng} />;
}
