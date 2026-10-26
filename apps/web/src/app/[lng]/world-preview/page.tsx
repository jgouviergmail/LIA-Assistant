import { notFound } from 'next/navigation';
import { WorldPreviewEntry } from '@/features/world/WorldEntry';
import { validateLanguage } from '@/i18n';
import { WorldProof } from '@/features/world/WorldProof';

/** Development-only: local art or explicitly isolated native proof accounts. */
export default async function WorldPreviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ lng: string }>;
  searchParams?: Promise<{ shared?: string; resume?: string }>;
}) {
  if (process.env.NODE_ENV !== 'development') notFound();
  const { lng } = await params;
  const query = await searchParams;
  return (
    <main className="p-2 sm:p-4">
      {process.env.WORLD_PROOF_PREVIEW === 'true' && query?.shared === '1' ? (
        <WorldProof
          lng={validateLanguage(lng)}
          resume={query.resume === '1'}
          translationFixture={process.env.WORLD_PROOF_TRANSLATION_FIXTURE === 'true'}
        />
      ) : (
        <WorldPreviewEntry lng={validateLanguage(lng)} />
      )}
    </main>
  );
}
