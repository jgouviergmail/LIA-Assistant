'use client';

import { ContactsTool } from '@/components/workbench/contacts/ContactsTool';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools/contacts`: the account's contacts, by hand (ADR-369). */
export default function ContactsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <ContactsTool lng={lng} />;
}
