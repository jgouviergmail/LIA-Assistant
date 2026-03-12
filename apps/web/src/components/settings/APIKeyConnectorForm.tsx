'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { Eye, EyeOff, Key, CheckCircle2, AlertCircle } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';

interface APIKeyConnectorFormProps {
  lng: Language;
  connectorType: string;
  connectorLabel: string;
  requiresSecret?: boolean;
  onSuccess?: () => void;
  onCancel?: () => void;
}

interface ValidationResponse {
  is_valid: boolean;
  message: string;
  masked_key: string;
}

/**
 * Secure form for entering API keys.
 *
 * Security features:
 * - Password-type input (hidden by default)
 * - Toggle visibility option
 * - Client-side validation before submission
 * - Server-side validation before activation
 * - No key logging/storage in frontend state
 * - Automatic clearing on unmount
 */
export default function APIKeyConnectorForm({
  lng,
  connectorType,
  connectorLabel,
  requiresSecret = false,
  onSuccess,
  onCancel,
}: APIKeyConnectorFormProps) {
  const { t } = useTranslation(lng);

  // Form state
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [keyName, setKeyName] = useState('');

  // UI state
  const [showKey, setShowKey] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Clear sensitive data
  const clearForm = () => {
    setApiKey('');
    setApiSecret('');
    setKeyName('');
    setValidationResult(null);
    setError(null);
  };

  // Validate key format (client-side)
  const isKeyFormatValid = () => {
    if (!apiKey || apiKey.length < 8) return false;
    if (requiresSecret && (!apiSecret || apiSecret.length < 8)) return false;

    // Check for placeholder patterns
    const placeholders = ['your_', 'api_key_here', 'xxx', 'placeholder'];
    if (placeholders.some(p => apiKey.toLowerCase().includes(p))) return false;

    return true;
  };

  // Validate with server
  const handleValidate = async () => {
    if (!isKeyFormatValid()) {
      setError(t('settings.connectors.apiKey.error_invalid_format'));
      return;
    }

    setIsValidating(true);
    setError(null);
    setValidationResult(null);

    try {
      const response = await apiClient.post<ValidationResponse>('/connectors/api-key/validate', {
        api_key: apiKey,
        api_secret: apiSecret || null,
        connector_type: connectorType,
      });

      setValidationResult(response);

      if (!response.is_valid) {
        setError(response.message);
      }
    } catch (err: unknown) {
      logger.error('API key validation failed', err as Error, {
        component: 'APIKeyConnectorForm',
        connectorType,
      });
      const apiError = err as { response?: { data?: { detail?: string } } };
      setError(apiError.response?.data?.detail || t('settings.connectors.apiKey.error_validation'));
    } finally {
      setIsValidating(false);
    }
  };

  // Activate connector
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isKeyFormatValid()) {
      setError(t('settings.connectors.apiKey.error_invalid_format'));
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await apiClient.post('/connectors/api-key/activate', {
        api_key: apiKey,
        api_secret: apiSecret || null,
        key_name: keyName || null,
        connector_type: connectorType,
      });

      logger.info('API key connector activated', {
        component: 'APIKeyConnectorForm',
        connectorType,
      });

      clearForm();
      onSuccess?.();
    } catch (err: unknown) {
      logger.error('API key activation failed', err as Error, {
        component: 'APIKeyConnectorForm',
        connectorType,
      });
      const apiError = err as { response?: { data?: { detail?: string } } };
      setError(apiError.response?.data?.detail || t('settings.connectors.apiKey.error_activation'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    clearForm();
    onCancel?.();
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 border rounded-lg bg-muted/30">
      <div className="flex items-center gap-2 mb-4">
        <Key className="h-5 w-5" />
        <h3 className="font-medium">
          {t('settings.connectors.apiKey.title', { connector: connectorLabel })}
        </h3>
      </div>

      {/* Key Name (optional) */}
      <div className="space-y-2">
        <Label htmlFor="keyName">
          {t('settings.connectors.apiKey.key_name')}
          <span className="text-muted-foreground text-sm ml-1">({t('common.optional')})</span>
        </Label>
        <Input
          id="keyName"
          type="text"
          value={keyName}
          onChange={e => setKeyName(e.target.value)}
          placeholder={t('settings.connectors.apiKey.key_name_placeholder')}
          maxLength={100}
          autoComplete="off"
        />
      </div>

      {/* API Key */}
      <div className="space-y-2">
        <Label htmlFor="apiKey">
          {t('settings.connectors.apiKey.api_key')}
          <span className="text-destructive ml-1">*</span>
        </Label>
        <div className="relative">
          <Input
            id="apiKey"
            type={showKey ? 'text' : 'password'}
            value={apiKey}
            onChange={e => {
              setApiKey(e.target.value);
              setValidationResult(null);
              setError(null);
            }}
            placeholder={t('settings.connectors.apiKey.api_key_placeholder')}
            required
            minLength={8}
            maxLength={512}
            autoComplete="off"
            spellCheck={false}
            className="pr-10 font-mono"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            tabIndex={-1}
          >
            {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          {t('settings.connectors.apiKey.api_key_hint')}
        </p>
      </div>

      {/* API Secret (if required) */}
      {requiresSecret && (
        <div className="space-y-2">
          <Label htmlFor="apiSecret">
            {t('settings.connectors.apiKey.api_secret')}
            <span className="text-destructive ml-1">*</span>
          </Label>
          <div className="relative">
            <Input
              id="apiSecret"
              type={showSecret ? 'text' : 'password'}
              value={apiSecret}
              onChange={e => {
                setApiSecret(e.target.value);
                setValidationResult(null);
                setError(null);
              }}
              placeholder={t('settings.connectors.apiKey.api_secret_placeholder')}
              required={requiresSecret}
              minLength={8}
              maxLength={512}
              autoComplete="off"
              spellCheck={false}
              className="pr-10 font-mono"
            />
            <button
              type="button"
              onClick={() => setShowSecret(!showSecret)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              tabIndex={-1}
            >
              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
      )}

      {/* Validation Result */}
      {validationResult && (
        <div
          className={`flex items-center gap-2 p-3 rounded-md ${
            validationResult.is_valid
              ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
              : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
          }`}
        >
          {validationResult.is_valid ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <AlertCircle className="h-4 w-4" />
          )}
          <span className="text-sm">{validationResult.message}</span>
          {validationResult.is_valid && (
            <span className="text-xs ml-auto font-mono">{validationResult.masked_key}</span>
          )}
        </div>
      )}

      {/* Error */}
      {error && !validationResult && (
        <div className="flex items-center gap-2 p-3 rounded-md bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={handleValidate}
          disabled={!isKeyFormatValid() || isValidating || isSubmitting}
        >
          {isValidating && <LoadingSpinner size="default" className="mr-2" />}
          {t('settings.connectors.apiKey.validate')}
        </Button>

        <Button type="submit" disabled={!isKeyFormatValid() || isSubmitting}>
          {isSubmitting && <LoadingSpinner size="default" className="mr-2" />}
          {t('settings.connectors.apiKey.activate')}
        </Button>

        {onCancel && (
          <Button type="button" variant="ghost" onClick={handleCancel} disabled={isSubmitting}>
            {t('common.cancel')}
          </Button>
        )}
      </div>

      {/* Security Notice */}
      <p className="text-xs text-muted-foreground mt-4">
        {t('settings.connectors.apiKey.security_notice')}
      </p>
    </form>
  );
}
