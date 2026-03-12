import { Metadata } from 'next';
import Link from 'next/link';
import { RegisterForm } from '@/components/auth/register-form';
import { OAuthButtons } from '@/components/auth/oauth-buttons';
import { initI18next } from '@/i18n';

interface RegisterPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: RegisterPageProps): Promise<Metadata> {
  const { lng } = await params;
  const { t } = await initI18next(lng);

  return {
    title: t('auth.metadata.register_title'),
    description: t('auth.metadata.register_description'),
  };
}

export default async function RegisterPage({ params }: RegisterPageProps) {
  const { lng } = await params;
  const { t } = await initI18next(lng);
  const loginHref = lng === 'fr' ? '/login' : `/${lng}/login`;

  return (
    <div>
      <div className="text-center mb-8 space-y-3">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text tracking-tight">
          {t('auth.register_page.title')}
        </h1>
        <p className="text-muted-foreground text-base">{t('auth.register_page.subtitle')}</p>
      </div>

      <OAuthButtons mode="register" />

      <div className="mt-6">
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-3 bg-background text-muted-foreground font-medium">
              {t('auth.register_page.divider')}
            </span>
          </div>
        </div>

        <div className="mt-6">
          <RegisterForm />
        </div>
      </div>

      <div className="mt-8 text-center">
        <p className="text-sm text-muted-foreground">
          {t('auth.register_page.have_account')}{' '}
          <Link
            href={loginHref}
            className="font-semibold text-primary hover:text-primary/90 transition-colors underline-offset-4 hover:underline"
          >
            {t('auth.register_page.login_link')}
          </Link>
        </p>
      </div>
    </div>
  );
}
