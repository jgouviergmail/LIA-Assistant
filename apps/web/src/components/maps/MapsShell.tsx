import { BreadcrumbJsonLd } from '@/components/seo/JsonLd';
import { LandingHeader } from '@/components/landing/LandingHeader';
import { PublicFooter } from '@/components/layout/PublicFooter';
import { CosmicBackdrop } from '@/components/landing/cosmic/CosmicBackdrop';
import { CosmosDarkFirst } from '@/components/landing/cosmic/CosmosDarkFirst';
import { CosmosThemeDefault } from '@/components/landing/cosmic/CosmosThemeDefault';
import type { Language } from '@/i18n/settings';
import '@/styles/maps.css';

/**
 * The frame of the four pages of `/maps`: the public site's calm cosmos scope,
 * its header and footer, and the breadcrumb search engines read.
 *
 * The section's stylesheet is imported here, so only these pages load it.
 */
export function MapsShell({
  lng,
  breadcrumb,
  children,
}: {
  lng: Language;
  breadcrumb: ReadonlyArray<{ name: string; url: string }>;
  children: React.ReactNode;
}) {
  return (
    <>
      <BreadcrumbJsonLd items={[...breadcrumb]} />
      <div className="landing-page cosmos cosmos-calm lia-maps min-h-screen">
        <CosmosDarkFirst />
        <CosmicBackdrop />
        <CosmosThemeDefault />
        <LandingHeader lng={lng} />
        <main className="lm-page">{children}</main>
        <PublicFooter lng={lng} />
      </div>
    </>
  );
}
