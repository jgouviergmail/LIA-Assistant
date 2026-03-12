'use client';

import { useMemo, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { Plug, CheckCircle2, Key, Save, AlertTriangle } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { toast } from 'sonner';
import { useState } from 'react';

// Import from extracted modules
import {
  GOOGLE_CONNECTOR_TYPES,
  APPLE_CONNECTOR_TYPES,
  MICROSOFT_CONNECTOR_TYPES,
  APPLE_CONNECTORS_METADATA,
  MICROSOFT_CONNECTORS_METADATA,
  API_KEY_CONNECTOR_TYPES,
  API_KEY_CONNECTORS,
  GOOGLE_CONNECTORS_METADATA,
  GOOGLE_AUTH_ENDPOINTS,
  MICROSOFT_AUTH_ENDPOINTS,
  MUTUAL_EXCLUSIVITY_MAP,
  type Connector,
  type ConnectorsResponse,
  isConnectorActive,
  isConnectorError,
  isConnectorTypeActive,
  isConnectorTypeExists,
  ConnectorIcon,
  ConnectedConnectorCard,
  ErrorConnectorCard,
  AvailableConnectorCard,
  LocationSettings,
  useGoogleOAuth,
  useMicrosoftOAuth,
  useBulkConnect,
  useConnectorPreferences,
} from './connectors';
import { AppleCredentialForm } from './connectors/AppleCredentialForm';
import { CONNECTOR_LABELS, type ConnectorType } from '@/constants/connectors';
import type { BaseSettingsProps } from '@/types/settings';

// Constants
const OAUTH_RECONNECT_PENDING_KEY = 'oauth_connectors_reconnect_pending';

export default function UserConnectorsSection({
  lng,
  collapsible = true,
}: BaseSettingsProps) {
  const { t } = useTranslation(lng);

  // State for API key input forms
  const [apiKeyInputs, setApiKeyInputs] = useState<Record<string, string>>({});
  const [activatingConnector, setActivatingConnector] = useState<string | null>(null);
  const [reconnectingConnector, setReconnectingConnector] = useState<string | null>(null);
  // Apple credential form: list of services to connect (null = form hidden)
  const [appleConnectTarget, setAppleConnectTarget] = useState<string[] | null>(null);

  // Connectors data query
  const { data, loading, setData, refetch } = useApiQuery<ConnectorsResponse>('/connectors', {
    componentName: 'UserConnectorsSection',
    initialData: { connectors: [] },
  });

  const connectors = useMemo(() => data?.connectors || [], [data?.connectors]);

  // Ref for the section container to observe visibility
  const sectionRef = useRef<HTMLDivElement>(null);
  // Track last fetch time to avoid too frequent refetches (initialized to now to prevent double fetch on mount)
  const lastFetchRef = useRef<number>(Date.now());
  // Minimum interval between refetches (5 seconds)
  const REFETCH_INTERVAL_MS = 5000;

  // Refetch when section becomes visible (handles navigation and scrolling)
  useEffect(() => {
    const element = sectionRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0];
        if (entry?.isIntersecting) {
          const now = Date.now();
          // Only refetch if enough time has passed since last fetch
          if (now - lastFetchRef.current > REFETCH_INTERVAL_MS) {
            lastFetchRef.current = now;
            refetch();
          }
        }
      },
      { threshold: 0.1 } // Trigger when 10% visible
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [refetch]);

  // Refetch when page becomes visible (tab focus)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const now = Date.now();
        if (now - lastFetchRef.current > REFETCH_INTERVAL_MS) {
          lastFetchRef.current = now;
          refetch();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [refetch]);

  // Check for OAuth return (post-reconnection) and refetch
  useEffect(() => {
    const checkOAuthReturn = () => {
      try {
        if (sessionStorage.getItem(OAUTH_RECONNECT_PENDING_KEY)) {
          sessionStorage.removeItem(OAUTH_RECONNECT_PENDING_KEY);
          // Force immediate refetch after OAuth return
          lastFetchRef.current = 0;
          refetch();
        }
      } catch {
        // sessionStorage not available
      }
    };

    // Check on mount
    checkOAuthReturn();

    // Listen for storage changes (cross-tab)
    window.addEventListener('storage', checkOAuthReturn);
    return () => window.removeEventListener('storage', checkOAuthReturn);
  }, [refetch]);

  // Delete mutation
  const { mutate: deleteConnector, loading: deleteLoading } = useApiMutation({
    method: 'DELETE',
    componentName: 'UserConnectorsSection',
  });

  // Hooks
  const { connect: connectGoogle } = useGoogleOAuth({
    onError: error => toast.error(error),
  });

  const { connect: connectMicrosoft } = useMicrosoftOAuth({
    onError: error => toast.error(error),
  });

  const { bulkConnecting, connectAllGoogle, connectAllMicrosoft } = useBulkConnect({
    connectors,
    loading,
    t,
  });

  const {
    savedPrefs,
    savingPreference,
    selectPreference,
  } = useConnectorPreferences({ connectors, t });

  // Handlers
  const handleDisconnect = async (connectorId: string) => {
    if (deleteLoading) return;
    if (!confirm(t('settings.connectors.disconnect_confirm'))) return;

    try {
      await deleteConnector(`/connectors/${connectorId}`);
      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          connectors: prev.connectors.filter(c => c.id !== connectorId),
        };
      });
    } catch {
      toast.error(t('settings.connectors.disconnect_error'));
    }
  };

  const handleActivateApiKeyConnector = async (connectorType: string, requiresKey: boolean) => {
    const apiKey = apiKeyInputs[connectorType];

    if (requiresKey && !apiKey?.trim()) {
      toast.error(t('settings.connectors.api_key.invalid_key'));
      return;
    }

    setActivatingConnector(connectorType);

    try {
      let result: Connector;

      // Google Places uses a dedicated activation endpoint (global API key on server)
      if (connectorType === 'google_places') {
        result = await apiClient.post<Connector>('/connectors/google-places/activate', {});
      } else {
        result = await apiClient.post<Connector>('/connectors/api-key/activate', {
          connector_type: connectorType,
          api_key: requiresKey ? apiKey.trim() : 'not_required',
          key_name: `${connectorType}_key`,
        });
      }

      setApiKeyInputs(prev => ({ ...prev, [connectorType]: '' }));
      if (result) {
        setData(prev => {
          if (!prev) return prev;
          return { ...prev, connectors: [...prev.connectors, result] };
        });
      }
      toast.success(t('settings.connectors.api_key.success'));
    } catch (error: unknown) {
      const apiError = error as { response?: { data?: { detail?: string } } };
      logger.error(`Failed to activate ${connectorType} connector`, error as Error, {
        component: 'UserConnectorsSection',
        connectorType,
      });
      toast.error(apiError.response?.data?.detail || t('settings.connectors.api_key.error'));
    } finally {
      setActivatingConnector(null);
    }
  };

  const handleReconnect = async (connectorType: string) => {
    const endpoint = GOOGLE_AUTH_ENDPOINTS[connectorType] || MICROSOFT_AUTH_ENDPOINTS[connectorType];
    if (!endpoint) {
      toast.error(t('settings.connectors.health.reconnect_failed'));
      return;
    }

    setReconnectingConnector(connectorType);

    try {
      // Fetch the OAuth authorization URL from the backend
      const response = await apiClient.get<{ authorization_url: string }>(endpoint);
      // Mark reconnection as pending for post-OAuth refetch
      sessionStorage.setItem(OAUTH_RECONNECT_PENDING_KEY, 'true');
      // Redirect to Google OAuth
      window.location.href = response.authorization_url;
    } catch (error) {
      logger.error('Failed to initiate OAuth reconnect', error as Error, {
        component: 'UserConnectorsSection',
        connectorType,
      });
      toast.error(t('settings.connectors.health.reconnect_failed'));
      setReconnectingConnector(null);
    }
  };

  // Filter connectors by type using helper functions (DRY)
  // Sort by GOOGLE_CONNECTORS_METADATA order for consistent display
  const sortByMetadataOrder = (a: Connector, b: Connector) => {
    const aIndex = GOOGLE_CONNECTORS_METADATA.findIndex(
      m => m.type === a.connector_type.toLowerCase() || m.checkTypes?.includes(a.connector_type.toLowerCase())
    );
    const bIndex = GOOGLE_CONNECTORS_METADATA.findIndex(
      m => m.type === b.connector_type.toLowerCase() || m.checkTypes?.includes(b.connector_type.toLowerCase())
    );
    return aIndex - bIndex;
  };

  const connectedOAuthConnectors = connectors
    .filter(
      c =>
        GOOGLE_CONNECTOR_TYPES.includes(c.connector_type.toLowerCase() as typeof GOOGLE_CONNECTOR_TYPES[number]) &&
        isConnectorActive(c)
    )
    .sort(sortByMetadataOrder);

  const connectedApiKeyConnectors = connectors.filter(
    c =>
      API_KEY_CONNECTOR_TYPES.includes(c.connector_type.toLowerCase() as typeof API_KEY_CONNECTOR_TYPES[number]) &&
      isConnectorActive(c)
  );

  // Connectors with ERROR status (need reconnection)
  const errorOAuthConnectors = connectors
    .filter(
      c =>
        GOOGLE_CONNECTOR_TYPES.includes(c.connector_type.toLowerCase() as typeof GOOGLE_CONNECTOR_TYPES[number]) &&
        isConnectorError(c)
    )
    .sort(sortByMetadataOrder);

  const errorMicrosoftConnectors = connectors.filter(
    c =>
      MICROSOFT_CONNECTOR_TYPES.includes(c.connector_type.toLowerCase() as typeof MICROSOFT_CONNECTOR_TYPES[number]) &&
      isConnectorError(c)
  );

  const connectedAppleConnectors = connectors.filter(
    c =>
      APPLE_CONNECTOR_TYPES.includes(c.connector_type.toLowerCase() as typeof APPLE_CONNECTOR_TYPES[number]) &&
      isConnectorActive(c)
  );

  const connectedMicrosoftConnectors = connectors
    .filter(
      c =>
        MICROSOFT_CONNECTOR_TYPES.includes(c.connector_type.toLowerCase() as typeof MICROSOFT_CONNECTOR_TYPES[number]) &&
        isConnectorActive(c)
    );

  // Check if any Google connectors are not connected AND don't exist at all
  // (connectors with ERROR status should show in error section, not available)
  const hasUnconnectedGoogle = GOOGLE_CONNECTORS_METADATA.some(
    meta => !isConnectorTypeExists(connectors, meta.type, meta.checkTypes)
  );

  // Check if Apple form should be shown (at least one Apple service not connected/in error)
  const hasUnconnectedApple = APPLE_CONNECTOR_TYPES.some(
    type => !isConnectorTypeExists(connectors, type)
  );

  // Check if Microsoft section should be shown
  const hasUnconnectedMicrosoft = MICROSOFT_CONNECTORS_METADATA.some(
    meta => !isConnectorTypeExists(connectors, meta.type)
  );

  // All active connector types (for mutual exclusivity checks)
  const activeConnectorTypes = connectors
    .filter(c => isConnectorActive(c))
    .map(c => c.connector_type.toLowerCase());

  // Unconnected Apple services (for "Connect All" button)
  const unconnectedAppleTypes = APPLE_CONNECTORS_METADATA
    .filter(meta => !isConnectorTypeActive(connectors, meta.type))
    .filter(meta => {
      // Exclude services blocked by mutual exclusivity
      const competingTypes = MUTUAL_EXCLUSIVITY_MAP[meta.type];
      return !competingTypes?.length || !competingTypes.some(c => activeConnectorTypes.includes(c));
    })
    .map(meta => meta.type);

  const content = (
    <div ref={sectionRef} className="space-y-6">
      {loading ? (
        <div className="p-6 flex items-center justify-center">
          <div className="flex items-center gap-3">
            <LoadingSpinner size="md" />
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          </div>
        </div>
      ) : (
        <>
          {/* ===================== CONNECTED SECTIONS ===================== */}

          {/* Connected Google Services */}
          {connectedOAuthConnectors.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-success" />
                {t('settings.connectors.connected_google')}
              </h3>
              <div className="space-y-2">
                {connectedOAuthConnectors.map(connector => (
                  <ConnectedConnectorCard
                    key={connector.id}
                    connector={connector}
                    lng={lng}
                    t={t}
                    deleteLoading={deleteLoading}
                    onDisconnect={handleDisconnect}
                    savedPrefs={savedPrefs[connector.id]}
                    savingPreference={savingPreference}
                    onSelectPreference={selectPreference}
                  >
                    {/* LocationSettings for Google Places */}
                    {connector.connector_type === 'google_places' && <LocationSettings t={t} />}
                  </ConnectedConnectorCard>
                ))}
              </div>
            </div>
          )}

          {/* Connected Apple iCloud Services */}
          {connectedAppleConnectors.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-success" />
                {t('settings.connectors.connected_apple')}
              </h3>
              <div className="space-y-2">
                {connectedAppleConnectors.map(connector => (
                  <ConnectedConnectorCard
                    key={connector.id}
                    connector={connector}
                    lng={lng}
                    t={t}
                    deleteLoading={deleteLoading}
                    onDisconnect={handleDisconnect}
                    savedPrefs={savedPrefs[connector.id]}
                    savingPreference={savingPreference}
                    onSelectPreference={selectPreference}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Connected Microsoft 365 Services */}
          {connectedMicrosoftConnectors.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-success" />
                {t('settings.connectors.connected_microsoft')}
              </h3>
              <div className="space-y-2">
                {connectedMicrosoftConnectors.map(connector => (
                  <ConnectedConnectorCard
                    key={connector.id}
                    connector={connector}
                    lng={lng}
                    t={t}
                    deleteLoading={deleteLoading}
                    onDisconnect={handleDisconnect}
                    savedPrefs={savedPrefs[connector.id]}
                    savingPreference={savingPreference}
                    onSelectPreference={selectPreference}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Connected External (API Key) Services */}
          {connectedApiKeyConnectors.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-success" />
                {t('settings.connectors.connected_api_key')}
              </h3>
              <div className="space-y-2">
                {connectedApiKeyConnectors.map(connector => (
                  <ConnectedConnectorCard
                    key={connector.id}
                    connector={connector}
                    lng={lng}
                    t={t}
                    deleteLoading={deleteLoading}
                    onDisconnect={handleDisconnect}
                  >
                    {/* LocationSettings for Google Places (global API key mode) */}
                    {connector.connector_type === 'google_places' && <LocationSettings t={t} />}
                  </ConnectedConnectorCard>
                ))}
              </div>
            </div>
          )}

          {/* ===================== ERROR SECTIONS ===================== */}

          {/* Error Google Connectors - Need Reconnection */}
          {errorOAuthConnectors.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-4 w-4" />
                {t('settings.connectors.health.critical_title')}
              </h3>
              <div className="space-y-2">
                {errorOAuthConnectors.map(connector => (
                  <ErrorConnectorCard
                    key={connector.id}
                    connector={connector}
                    t={t}
                    reconnecting={reconnectingConnector === connector.connector_type}
                    onReconnect={handleReconnect}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Error Microsoft Connectors - Need Reconnection */}
          {errorMicrosoftConnectors.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-medium flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-4 w-4" />
                {t('settings.connectors.health.critical_title')}
              </h3>
              <div className="space-y-2">
                {errorMicrosoftConnectors.map(connector => (
                  <ErrorConnectorCard
                    key={connector.id}
                    connector={connector}
                    t={t}
                    reconnecting={reconnectingConnector === connector.connector_type}
                    onReconnect={handleReconnect}
                  />
                ))}
              </div>
            </div>
          )}

          {/* ===================== AVAILABLE SECTIONS ===================== */}

          {/* Available Google Connectors */}
          {hasUnconnectedGoogle && (
            <div className="space-y-3 pt-4 border-t">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">{t('settings.connectors.available_google')}</h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={connectAllGoogle}
                  disabled={bulkConnecting}
                  className="gap-2"
                >
                  {bulkConnecting ? (
                    <LoadingSpinner size="default" />
                  ) : (
                    <Plug className="h-4 w-4" />
                  )}
                  {t('settings.connectors.google.connect_all')}
                </Button>
              </div>
              <div className="space-y-2">
                {GOOGLE_CONNECTORS_METADATA.map(meta => {
                  // Don't show in available if exists (active OR error)
                  const exists = isConnectorTypeExists(connectors, meta.type, meta.checkTypes);
                  if (exists) return null;

                  const competingTypes = MUTUAL_EXCLUSIVITY_MAP[meta.type];
                  const activeCompetitor = competingTypes?.find(c => activeConnectorTypes.includes(c));
                  const isBlocked = !!activeCompetitor;

                  return (
                    <AvailableConnectorCard
                      key={meta.type}
                      connectorType={meta.type}
                      label={t(meta.labelKey)}
                      description={t(meta.descriptionKey)}
                      onConnect={() => connectGoogle(meta.type)}
                      connectTitle={t('settings.connectors.google.connect')}
                      isBlocked={isBlocked}
                      blockedMessage={isBlocked ? t('settings.connectors.google.service_blocked', {
                        competing: CONNECTOR_LABELS[activeCompetitor as ConnectorType] || activeCompetitor,
                      }) : undefined}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Available Apple iCloud Connectors */}
          {hasUnconnectedApple && (
            <div className="space-y-3 pt-4 border-t">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium flex items-center gap-2">
                  {t('settings.connectors.apple.title')}
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAppleConnectTarget(unconnectedAppleTypes)}
                  disabled={unconnectedAppleTypes.length === 0}
                  className="gap-2"
                >
                  <Plug className="h-4 w-4" />
                  {t('settings.connectors.apple.connect_all')}
                </Button>
              </div>

              {/* Apple credential form (shown when a service is selected) */}
              {appleConnectTarget && (
                <AppleCredentialForm
                  lng={lng}
                  services={appleConnectTarget}
                  onActivated={() => {
                    setAppleConnectTarget(null);
                    refetch();
                  }}
                  onCancel={() => setAppleConnectTarget(null)}
                />
              )}

              {/* Individual Apple service cards */}
              {!appleConnectTarget && (
                <div className="space-y-2">
                  {APPLE_CONNECTORS_METADATA.map(meta => {
                    if (isConnectorTypeExists(connectors, meta.type)) return null;

                    const competingTypes = MUTUAL_EXCLUSIVITY_MAP[meta.type];
                    const activeCompetitor = competingTypes?.find(c => activeConnectorTypes.includes(c));
                    const isBlocked = !!activeCompetitor;

                    return (
                      <AvailableConnectorCard
                        key={meta.type}
                        connectorType={meta.type}
                        label={t(meta.labelKey)}
                        description={t(meta.descriptionKey)}
                        onConnect={() => setAppleConnectTarget([meta.type])}
                        connectTitle={t('settings.connectors.apple.connect')}
                        isBlocked={isBlocked}
                        blockedMessage={isBlocked ? t('settings.connectors.apple.service_blocked', {
                          competing: CONNECTOR_LABELS[activeCompetitor as ConnectorType] || activeCompetitor,
                        }) : undefined}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Available Microsoft 365 Services */}
          {hasUnconnectedMicrosoft && (
            <div className="space-y-3 pt-4 border-t">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium flex items-center gap-2">
                  {t('settings.connectors.microsoft.title')}
                </h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={connectAllMicrosoft}
                  disabled={bulkConnecting}
                  className="gap-2"
                >
                  {bulkConnecting ? (
                    <LoadingSpinner size="default" />
                  ) : (
                    <Plug className="h-4 w-4" />
                  )}
                  {t('settings.connectors.microsoft.connect_all')}
                </Button>
              </div>
              <div className="space-y-2">
                {MICROSOFT_CONNECTORS_METADATA.map(meta => {
                  if (isConnectorTypeExists(connectors, meta.type)) return null;

                  const competingTypes = MUTUAL_EXCLUSIVITY_MAP[meta.type];
                  const activeCompetitor = competingTypes?.find(c => activeConnectorTypes.includes(c));
                  const isBlocked = !!activeCompetitor;

                  return (
                    <AvailableConnectorCard
                      key={meta.type}
                      connectorType={meta.type}
                      label={t(meta.labelKey)}
                      description={t(meta.descriptionKey)}
                      onConnect={() => connectMicrosoft(meta.type)}
                      connectTitle={t('settings.connectors.microsoft.connect')}
                      isBlocked={isBlocked}
                      blockedMessage={isBlocked ? t('settings.connectors.microsoft.service_blocked', {
                        competing: CONNECTOR_LABELS[activeCompetitor as ConnectorType] || activeCompetitor,
                      }) : undefined}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Available External (API Key) Connectors */}
          <div className="space-y-3 pt-4 border-t">
            <h3 className="text-sm font-medium flex items-center gap-2">
              <Key className="h-4 w-4" />
              {t('settings.connectors.available_external')}
            </h3>
            <p className="text-sm text-muted-foreground">
              {t('settings.connectors.api_key.description')}
            </p>
            <div className="space-y-2">
              {API_KEY_CONNECTORS.map(connector => {
                const isConnected = isConnectorTypeActive(connectors, connector.type);
                const isActivating = activatingConnector === connector.type;

                if (isConnected) return null;

                return (
                  <div
                    key={connector.type}
                    className="flex flex-col gap-3 p-4 border rounded-lg hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <ConnectorIcon connectorType={connector.type} />
                        <div>
                          <div className="font-medium">
                            {t(`settings.connectors.${connector.type}.label`)}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {t(`settings.connectors.${connector.type}.description`)}
                          </div>
                        </div>
                      </div>
                    </div>

                    {connector.requiresKey ? (
                      <div className="flex gap-2">
                        <Input
                          type="password"
                          placeholder={t('settings.connectors.api_key.key_placeholder')}
                          value={apiKeyInputs[connector.type] || ''}
                          onChange={e =>
                            setApiKeyInputs(prev => ({
                              ...prev,
                              [connector.type]: e.target.value,
                            }))
                          }
                          className="flex-1"
                          disabled={isActivating}
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleActivateApiKeyConnector(connector.type, true)}
                          disabled={isActivating || !apiKeyInputs[connector.type]?.trim()}
                          className="text-primary hover:text-primary hover:bg-primary/10"
                          title={t('settings.connectors.api_key.activate')}
                        >
                          {isActivating ? (
                            <LoadingSpinner size="default" />
                          ) : (
                            <Save className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground italic">
                          {t(`settings.connectors.${connector.type}.no_key_required`)}
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleActivateApiKeyConnector(connector.type, false)}
                          disabled={isActivating}
                          className="text-green-600 hover:text-green-700 hover:bg-green-500/10 dark:text-green-500 dark:hover:text-green-400"
                          title={t('settings.connectors.api_key.activate')}
                        >
                          {isActivating ? (
                            <LoadingSpinner size="default" />
                          ) : (
                            <Plug className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                    )}

                    {connector.requiresKey && (
                      <p className="text-xs text-muted-foreground">
                        {t(`settings.connectors.${connector.type}.get_key`)}
                      </p>
                    )}
                  </div>
                );
              })}

              {/* All API Key connectors connected */}
              {API_KEY_CONNECTORS.every(c => isConnectorTypeActive(connectors, c.type)) && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {t('settings.connectors.all_connected')}
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="connectors"
      title={t('settings.connectors.my_connectors')}
      description={t('settings.connectors.my_connectors_description')}
      icon={Plug}
    >
      {content}
    </SettingsSection>
  );
}
