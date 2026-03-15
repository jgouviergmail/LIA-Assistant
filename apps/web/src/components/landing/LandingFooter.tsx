import { initI18next } from '@/i18n';
import Image from 'next/image';

interface LandingFooterProps {
  lng: string;
}

export async function LandingFooter({ lng }: LandingFooterProps) {
  const { t } = await initI18next(lng);
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-border py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col mobile:flex-row items-center justify-between gap-4">
          {/* Logo + copyright */}
          <div className="flex items-center gap-3">
            <Image
              src="/v4-lia-brain.svg"
              alt="LIA"
              width={24}
              height={24}
              className="rounded-md"
            />
            <span className="text-sm text-muted-foreground">
              {t('landing.footer.copyright', { year })} · v{process.env.NEXT_PUBLIC_APP_VERSION}
            </span>
          </div>

          {/* Links */}
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <a
              href="#security"
              className="hover:text-foreground transition-colors"
            >
              {t('landing.footer.privacy')}
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
