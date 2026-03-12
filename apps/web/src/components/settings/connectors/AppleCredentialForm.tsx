/**
 * AppleCredentialForm component.
 * Form for Apple iCloud connection: Apple ID + App-Specific Password.
 * Single-step: validates and activates in one click.
 */

'use client';

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Eye, EyeOff, Shield, ExternalLink, Loader2, X } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useAppleConnect } from './hooks/useAppleConnect';
import { ConnectorIcon } from './ConnectorIcon';
import { APPLE_CONNECTORS_METADATA } from './constants';

// App-specific password format: xxxx-xxxx-xxxx-xxxx (lowercase letters only)
const APP_PASSWORD_PATTERN = /^[a-z]{4}-[a-z]{4}-[a-z]{4}-[a-z]{4}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface AppleCredentialFormProps {
  /** Language code for i18n */
  lng: Language;
  /** Services to activate */
  services: string[];
  /** Callback after successful activation */
  onActivated?: () => void;
  /** Callback to close/cancel the form */
  onCancel?: () => void;
}

export function AppleCredentialForm({
  lng,
  services,
  onActivated,
  onCancel,
}: AppleCredentialFormProps) {
  const { t } = useTranslation(lng);
  const [appleId, setAppleId] = useState('');
  const [appPassword, setAppPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const { connect, connecting } = useAppleConnect({
    onError: (error) => toast.error(error),
    onSuccess: () => {
      toast.success(t('settings.connectors.apple.activate_success'));
      setAppleId('');
      setAppPassword('');
      onActivated?.();
    },
  });

  // Client-side validation
  const isAppleIdValid = EMAIL_PATTERN.test(appleId);
  const isPasswordValid = APP_PASSWORD_PATTERN.test(appPassword);
  const canConnect = isAppleIdValid && isPasswordValid;

  const handleConnect = useCallback(async () => {
    await connect(appleId, appPassword, services);
  }, [appleId, appPassword, services, connect]);

  // Resolve service labels for display
  const serviceLabels = services.map((type) => {
    const meta = APPLE_CONNECTORS_METADATA.find((m) => m.type === type);
    return meta ? t(meta.labelKey) : type;
  });

  const isBulk = services.length > 1;

  return (
    <div className="space-y-4 p-4 border rounded-lg bg-card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isBulk ? (
            <>
              <span className="text-xl"></span>
              <h3 className="font-medium">{t('settings.connectors.apple.connect')}</h3>
            </>
          ) : (
            <>
              <ConnectorIcon connectorType={services[0]} className="h-6 w-6" />
              <h3 className="font-medium">{serviceLabels[0]}</h3>
            </>
          )}
        </div>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        {t('settings.connectors.apple.connect_description')}
      </p>

      {/* Security notice */}
      <div className="flex items-start gap-2 p-3 bg-muted/50 rounded-md">
        <Shield className="h-4 w-4 mt-0.5 text-green-600" />
        <div className="text-xs text-muted-foreground space-y-1">
          <p>{t('settings.connectors.apple.two_fa_required')}</p>
          <a
            href={t('settings.connectors.apple.app_password_url')}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-primary hover:underline"
          >
            {t('settings.connectors.apple.app_password_link')}
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>

      {/* Apple ID input */}
      <div className="space-y-2">
        <Label htmlFor="apple-id">{t('settings.connectors.apple.apple_id_label')}</Label>
        <Input
          id="apple-id"
          type="email"
          placeholder={t('settings.connectors.apple.apple_id_placeholder')}
          value={appleId}
          onChange={(e) => setAppleId(e.target.value)}
          disabled={connecting}
        />
      </div>

      {/* App-specific password input */}
      <div className="space-y-2">
        <Label htmlFor="app-password">
          {t('settings.connectors.apple.app_password_label')}
        </Label>
        <div className="relative">
          <Input
            id="app-password"
            type={showPassword ? 'text' : 'password'}
            placeholder={t('settings.connectors.apple.app_password_placeholder')}
            value={appPassword}
            onChange={(e) => setAppPassword(e.target.value)}
            disabled={connecting}
            className="pr-10"
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          {t('settings.connectors.apple.app_password_help')}
        </p>
      </div>

      {/* Services to activate (bulk mode) */}
      {isBulk && (
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">
            {t('settings.connectors.apple.services_to_activate')}
          </Label>
          <div className="flex flex-wrap gap-2">
            {services.map((type) => {
              const meta = APPLE_CONNECTORS_METADATA.find((m) => m.type === type);
              return (
                <div key={type} className="flex items-center gap-1.5 px-2 py-1 bg-muted rounded-md">
                  <ConnectorIcon connectorType={type} className="h-4 w-4" />
                  <span className="text-xs font-medium">
                    {meta ? t(meta.labelKey) : type}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Connect button */}
      <Button
        onClick={handleConnect}
        disabled={!canConnect || connecting}
        className="w-full"
        size="sm"
      >
        {connecting ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            {t('settings.connectors.apple.connecting')}...
          </>
        ) : (
          t('settings.connectors.apple.connect')
        )}
      </Button>
    </div>
  );
}
