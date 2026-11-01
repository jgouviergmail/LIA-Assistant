'use client';

import { MailTool } from '@/components/workbench/mail/MailTool';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools/mail`: the account's mailbox, by hand (ADR-369). */
export default function MailPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <MailTool lng={lng} />;
}
