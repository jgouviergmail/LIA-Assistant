import { redirect } from 'next/navigation';
import { fallbackLng, isLanguage } from '@/i18n/settings';

/** Keep existing notification, chat-card and bookmark links usable. */
export default async function SmsPage({
  params,
  searchParams,
}: {
  params: Promise<{ lng: string }>;
  searchParams: Promise<{ message?: string | string[] }>;
}) {
  const { lng } = await params;
  const { message } = await searchParams;
  const query = new URLSearchParams({ section: 'sms' });
  if (typeof message === 'string') query.set('message', message);
  redirect(`/${isLanguage(lng) ? lng : fallbackLng}/dashboard/settings?${query}`);
}
