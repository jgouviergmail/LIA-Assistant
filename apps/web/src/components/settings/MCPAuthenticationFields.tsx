'use client';

import type { Dispatch, SetStateAction } from 'react';
import type { TFunction } from 'i18next';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { UserMCPAuthType } from '@/hooks/useUserMCPServers';
import type { MCPServerFormSource, MCPServerFormState } from '@/lib/mcp-server-form';

interface Props {
  id: string;
  form: MCPServerFormState;
  setForm: Dispatch<SetStateAction<MCPServerFormState>>;
  editingServer: MCPServerFormSource | null;
  t: TFunction;
}
function APIKeyFields({ id, form, setForm, editingServer, t }: Props) {
  return (<>
              <div className="space-y-3">
                <Label htmlFor={`${id}-mcp-api-key`}>{t('settings.mcp.field_api_key')}</Label>
                <Input
                  id={`${id}-mcp-api-key`}
                  value={form.api_key}
                  onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                  type="password"
                  placeholder={
                    editingServer?.has_credentials
                      ? t('settings.mcp.field_credentials_saved')
                      : editingServer
                        ? t('settings.mcp.field_keep_existing')
                        : ''
                  }
                />
                {editingServer?.has_credentials && !form.api_key && (
                  <p className="text-xs text-muted-foreground">
                    {t('settings.mcp.field_credentials_hint')}
                  </p>
                )}
              </div>
              <div className="space-y-3">
                <Label htmlFor={`${id}-mcp-header-name`}>{t('settings.mcp.field_header_name')}</Label>
                <Input
                  id={`${id}-mcp-header-name`}
                  value={form.header_name}
                  onChange={e => setForm(f => ({ ...f, header_name: e.target.value }))}
                  placeholder="X-API-Key"
                />
              </div>
            </>);
}

function BearerFields({ id, form, setForm, editingServer, t }: Props) {
  return (<div className="space-y-3">
              <Label htmlFor={`${id}-mcp-bearer-token`}>{t('settings.mcp.field_bearer_token')}</Label>
              <Input
                id={`${id}-mcp-bearer-token`}
                value={form.bearer_token}
                onChange={e => setForm(f => ({ ...f, bearer_token: e.target.value }))}
                type="password"
                placeholder={
                  editingServer?.has_credentials
                    ? t('settings.mcp.field_credentials_saved')
                    : editingServer
                      ? t('settings.mcp.field_keep_existing')
                      : ''
                }
              />
              {editingServer?.has_credentials && !form.bearer_token && (
                <p className="text-xs text-muted-foreground">
                  {t('settings.mcp.field_credentials_hint')}
                </p>
              )}
            </div>);
}

function OAuthFields({ id, form, setForm, editingServer, t }: Props) {
  return (<>
              <div className="space-y-3">
                <Label htmlFor={`${id}-mcp-oauth-client-id`}>
                  {t('settings.mcp.field_oauth_client_id')}{' '}
                  <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
                </Label>
                <Input
                  id={`${id}-mcp-oauth-client-id`}
                  value={form.oauth_client_id}
                  onChange={e => setForm(f => ({ ...f, oauth_client_id: e.target.value }))}
                  placeholder={
                    editingServer?.has_oauth_credentials
                      ? t('settings.mcp.field_credentials_saved')
                      : ''
                  }
                />
                {editingServer?.has_oauth_credentials && !form.oauth_client_id && (
                  <p className="text-xs text-muted-foreground">
                    {t('settings.mcp.field_credentials_hint')}
                  </p>
                )}
              </div>
              <div className="space-y-3">
                <Label htmlFor={`${id}-mcp-oauth-client-secret`}>
                  {t('settings.mcp.field_oauth_client_secret')}{' '}
                  <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
                </Label>
                <Input
                  id={`${id}-mcp-oauth-client-secret`}
                  value={form.oauth_client_secret}
                  onChange={e => setForm(f => ({ ...f, oauth_client_secret: e.target.value }))}
                  type="password"
                  placeholder={
                    editingServer?.has_oauth_credentials
                      ? t('settings.mcp.field_credentials_saved')
                      : ''
                  }
                />
                {editingServer?.has_oauth_credentials && !form.oauth_client_secret && (
                  <p className="text-xs text-muted-foreground">
                    {t('settings.mcp.field_credentials_hint')}
                  </p>
                )}
              </div>
              <div className="space-y-3">
                <Label htmlFor={`${id}-mcp-oauth-scopes`}>
                  {t('settings.mcp.field_oauth_scopes')}{' '}
                  <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
                </Label>
                <Input
                  id={`${id}-mcp-oauth-scopes`}
                  value={form.oauth_scopes}
                  onChange={e => setForm(f => ({ ...f, oauth_scopes: e.target.value }))}
                  placeholder={t('settings.mcp.field_oauth_scopes_placeholder')}
                />
                <p className="text-xs text-muted-foreground">
                  {t('settings.mcp.field_oauth_scopes_help')}
                </p>
              </div>
            </>);
}
export function MCPAuthenticationFields(props: Props) {
  const { id, form, setForm, t } = props;
  return <>

          <div className="space-y-3">
            <Label htmlFor={`${id}-mcp-auth`}>{t('settings.mcp.field_auth_type')}</Label>
            <Select
              value={form.auth_type}
              onValueChange={v => setForm(f => ({ ...f, auth_type: v as UserMCPAuthType }))}
            >
              <SelectTrigger id={`${id}-mcp-auth`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('settings.mcp.auth_none')}</SelectItem>
                <SelectItem value="api_key">{t('settings.mcp.auth_api_key')}</SelectItem>
                <SelectItem value="bearer">{t('settings.mcp.auth_bearer')}</SelectItem>
                <SelectItem value="oauth2">{t('settings.mcp.auth_oauth2')}</SelectItem>
              </SelectContent>
            </Select>
          </div>

    {form.auth_type === 'api_key' && <APIKeyFields {...props} />}
    {form.auth_type === 'bearer' && <BearerFields {...props} />}
    {form.auth_type === 'oauth2' && <OAuthFields {...props} />}
  </>;
}
