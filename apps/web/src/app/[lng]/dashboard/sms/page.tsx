'use client';

import { SmsWorkspace } from '@/components/sms/SmsWorkspace';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/**
 * The « SMS » destination: consult, block, erase. Every link a notification, a
 * chat card or a bookmark carries (`?message=`) opens here, on that message.
 */
export default function SmsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <SmsWorkspace lng={lng} />;
}
