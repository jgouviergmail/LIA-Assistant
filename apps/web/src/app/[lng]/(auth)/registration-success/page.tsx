'use client';

import Link from 'next/link';
import { MailCheck, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

/**
 * Page displayed after successful registration.
 *
 * Instructs the user to check their email (including spam/junk folder)
 * for the verification link before their account can be activated.
 */
export default function RegistrationSuccessPage() {
  const { t } = useTranslation();

  return (
    <div className="text-center space-y-6">
      <div className="flex justify-center">
        <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
          <MailCheck className="h-8 w-8 text-green-600 dark:text-green-400" />
        </div>
      </div>

      <h1 className="text-2xl font-bold text-foreground">
        {t('auth.registration_success.title')}
      </h1>

      <p className="text-muted-foreground">
        {t('auth.registration_success.message')}
      </p>

      {/* Spam warning */}
      <div className="bg-amber-50 dark:bg-amber-950/50 border-l-4 border-amber-500 p-4 rounded-r-lg text-left">
        <div className="flex gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-amber-700 dark:text-amber-300">
            <strong>{t('auth.registration_success.spam_warning_title')}</strong>{' '}
            {t('auth.registration_success.spam_warning_message')}
          </p>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        {t('auth.registration_success.link_expires')}
      </p>

      <Button asChild className="mt-4">
        <Link href="/login">{t('auth.registration_success.back_to_login')}</Link>
      </Button>
    </div>
  );
}
