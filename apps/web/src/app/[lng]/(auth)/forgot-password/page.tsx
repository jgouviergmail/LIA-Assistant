'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Mail, CheckCircle2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { TurnstileWidget } from '@/components/auth/TurnstileWidget';
import { useTurnstileDoor } from '@/hooks/useTurnstileDoor';
import { apiClient } from '@/lib/api-client';
import { turnstileErrorKey, turnstileHeaders } from '@/lib/turnstile';
import { useTranslation, Trans } from 'react-i18next';

type Status = 'form' | 'loading' | 'success';

export default function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [status, setStatus] = useState<Status>('form');
  const [email, setEmail] = useState('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const botCheck = useTurnstileDoor('password_reset');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMessage('');
    if (!botCheck.ready) {
      // Waiting cannot load a widget that failed: say which it is.
      setErrorMessage(
        t(botCheck.failed ? 'auth.turnstile.load_failed' : 'auth.turnstile.required')
      );
      return;
    }
    setStatus('loading');

    try {
      await apiClient.post(
        '/auth/request-password-reset',
        { email },
        turnstileHeaders(botCheck.token)
      );
      setStatus('success');
    } catch (error) {
      // The answer never says whether the address has an account: every failure
      // shows the same confirmation — except a refused or unavailable bot check,
      // which is about the visitor, not the address (ADR-364).
      const botCheckRefusal = turnstileErrorKey(error);
      if (botCheckRefusal) {
        setErrorMessage(t(botCheckRefusal));
        setStatus('form');
      } else {
        setStatus('success');
      }
    } finally {
      // The API spent the token, whatever it answered.
      botCheck.spent();
    }
  }

  if (status === 'success') {
    return (
      <div className="text-center space-y-6">
        <div className="flex justify-center">
          <CheckCircle2 className="h-16 w-16 text-success" />
        </div>
        <h1 className="text-2xl font-bold">{t('auth.forgot_password.success_title')}</h1>
        <p className="text-muted-foreground">
          <Trans
            i18nKey="auth.forgot_password.success_message"
            values={{ email }}
            components={{ strong: <strong /> }}
          />
        </p>
        <p className="text-sm text-muted-foreground">{t('auth.forgot_password.success_hint')}</p>
        <Button asChild className="mt-4">
          <Link href="/login">{t('auth.forgot_password.back_to_login')}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-3">
        <div className="flex justify-center">
          <Mail className="h-12 w-12 text-primary" />
        </div>
        <h1 className="text-2xl font-bold">{t('auth.forgot_password.title')}</h1>
        <p className="text-muted-foreground">{t('auth.forgot_password.subtitle')}</p>
      </div>

      {errorMessage && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg text-sm">
          {errorMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">{t('auth.forgot_password.email_label')}</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder={t('auth.forgot_password.email_placeholder')}
            required
          />
        </div>

        {botCheck.siteKey && (
          <TurnstileWidget
            siteKey={botCheck.siteKey}
            action="password_reset"
            onToken={botCheck.onToken}
            onFailure={botCheck.onFailure}
            resetSignal={botCheck.resetSignal}
          />
        )}

        <Button type="submit" className="w-full" disabled={status === 'loading'}>
          {status === 'loading'
            ? t('auth.forgot_password.submitting')
            : t('auth.forgot_password.submit')}
        </Button>
      </form>

      <div className="text-center">
        <Link
          href="/login"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('auth.forgot_password.back_to_login')}
        </Link>
      </div>
    </div>
  );
}
