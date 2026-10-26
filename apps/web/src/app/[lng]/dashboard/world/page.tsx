import { WorldEntry } from '@/features/world/WorldEntry';
import { validateLanguage } from '@/i18n';

export default async function WorldPage({ params }: { params: Promise<{ lng: string }> }) {
  const { lng } = await params;
  return <WorldEntry lng={validateLanguage(lng)} />;
}
