import { Metadata } from 'next';
import Link from 'next/link';
import { LoginForm } from '@/components/auth/login-form';
import { OAuthButtons } from '@/components/auth/oauth-buttons';
import { initI18next } from '@/i18n';

interface LoginPageProps {
  params: Promise<{ lng: string }>;
}

export async function generateMetadata({ params }: LoginPageProps): Promise<Metadata> {
  const { lng } = await params;
  const { t } = await initI18next(lng);

  return {
    title: t('auth.metadata.login_title'),
    description: t('auth.metadata.login_description'),
  };
}

export default async function LoginPage({ params }: LoginPageProps) {
  const { lng } = await params;
  const { t } = await initI18next(lng);
  const registerHref = lng === 'fr' ? '/register' : `/${lng}/register`;

  return (
    <div>
      <div className="text-center mb-8 space-y-3">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text tracking-tight">
          {t('auth.login_page.title')}
        </h1>
        <p className="text-muted-foreground text-base">{t('auth.login_page.subtitle')}</p>
      </div>

      <OAuthButtons />

      <div className="mt-6">
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-3 bg-background text-muted-foreground font-medium">
              {t('auth.login_page.divider')}
            </span>
          </div>
        </div>

        <div className="mt-6">
          <LoginForm />
        </div>
      </div>

      <div className="mt-8 text-center">
        <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3">
          <p className="text-sm text-foreground">
            {t('auth.login_page.no_account')}{' '}
            <Link
              href={registerHref}
              className="font-bold text-primary hover:text-primary/80 transition-colors underline underline-offset-4"
            >
              {t('auth.login_page.signup_link')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
