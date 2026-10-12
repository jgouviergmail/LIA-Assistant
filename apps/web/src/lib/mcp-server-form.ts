import type {
  UserMCPAuthType,
  UserMCPServer,
  UserMCPServerCreate,
  UserMCPServerUpdate,
} from '@/hooks/useUserMCPServers';

export type MCPServerFormSource = Pick<
  UserMCPServer,
  | 'id'
  | 'name'
  | 'url'
  | 'auth_type'
  | 'header_name'
  | 'oauth_scopes'
  | 'domain_description'
  | 'timeout_seconds'
  | 'iterative_mode'
  | 'has_credentials'
  | 'has_oauth_credentials'
>;

/** The original settings form and private command form share the same field policy. */
export interface MCPServerFormState {
  name: string;
  url: string;
  auth_type: UserMCPAuthType;
  api_key: string;
  header_name: string;
  bearer_token: string;
  oauth_client_id: string;
  oauth_client_secret: string;
  oauth_scopes: string;
  domain_description: string;
  timeout_seconds: number;
  iterative_mode: boolean;
}

export function emptyMCPServerForm(): MCPServerFormState {
  return {
    name: '',
    url: '',
    auth_type: 'none',
    api_key: '',
    header_name: 'X-API-Key',
    bearer_token: '',
    oauth_client_id: '',
    oauth_client_secret: '',
    oauth_scopes: '',
    domain_description: '',
    timeout_seconds: 30,
    iterative_mode: false,
  };
}

export function editMCPServerForm(server: MCPServerFormSource): MCPServerFormState {
  return {
    ...emptyMCPServerForm(),
    name: server.name,
    url: server.url,
    auth_type: server.auth_type,
    header_name: server.header_name || 'X-API-Key',
    oauth_scopes: server.oauth_scopes ?? '',
    domain_description: server.domain_description ?? '',
    timeout_seconds: server.timeout_seconds,
    iterative_mode: server.iterative_mode ?? false,
  };
}

export function isMCPServerFormValid(form: MCPServerFormState, editing: boolean): boolean {
  return (
    form.name.trim() !== '' &&
    form.url.trim() !== '' &&
    (form.auth_type !== 'api_key' || form.api_key.trim() !== '' || editing) &&
    (form.auth_type !== 'bearer' || form.bearer_token.trim() !== '' || editing)
  );
}

function authenticationValues(form: MCPServerFormState): UserMCPServerUpdate {
  if (form.auth_type === 'api_key')
    return {
      ...(form.api_key && { api_key: form.api_key }),
      header_name: form.header_name,
    };
  if (form.auth_type === 'bearer')
    return { ...(form.bearer_token && { bearer_token: form.bearer_token }) };
  if (form.auth_type === 'oauth2')
    return {
      ...(form.oauth_client_id && { oauth_client_id: form.oauth_client_id }),
      ...(form.oauth_client_secret && { oauth_client_secret: form.oauth_client_secret }),
      ...(form.oauth_scopes && { oauth_scopes: form.oauth_scopes }),
    };
  return {};
}

/** Blank secrets preserve stored ciphertext. Only the chosen auth scheme is submitted. */
function authenticationUpdateValues(
  form: MCPServerFormState,
  existing: MCPServerFormSource
): UserMCPServerUpdate {
  const values = authenticationValues(form);
  if (values.header_name === (existing.header_name || 'X-API-Key')) delete values.header_name;
  if (form.auth_type === 'oauth2' && form.oauth_scopes !== (existing.oauth_scopes ?? ''))
    values.oauth_scopes = form.oauth_scopes;
  else delete values.oauth_scopes;
  return values;
}

export function mcpServerFormValues(form: MCPServerFormState): UserMCPServerCreate;
export function mcpServerFormValues(
  form: MCPServerFormState,
  existing: MCPServerFormSource
): UserMCPServerUpdate;
export function mcpServerFormValues(
  form: MCPServerFormState,
  existing: MCPServerFormSource | null
): UserMCPServerUpdate | UserMCPServerCreate;
export function mcpServerFormValues(
  form: MCPServerFormState,
  existing?: MCPServerFormSource | null
): UserMCPServerUpdate | UserMCPServerCreate {
  if (!existing)
    return {
      name: form.name,
      url: form.url,
      auth_type: form.auth_type,
      timeout_seconds: form.timeout_seconds,
      iterative_mode: form.iterative_mode,
      ...authenticationValues(form),
      ...(form.domain_description && { domain_description: form.domain_description }),
    };
  const values = authenticationUpdateValues(form, existing);
  if (form.name !== existing.name) values.name = form.name;
  if (form.url !== existing.url) values.url = form.url;
  if (form.auth_type !== existing.auth_type) values.auth_type = form.auth_type;
  if (form.timeout_seconds !== existing.timeout_seconds)
    values.timeout_seconds = form.timeout_seconds;
  if (form.iterative_mode !== existing.iterative_mode) values.iterative_mode = form.iterative_mode;
  if (form.domain_description !== (existing.domain_description ?? ''))
    values.domain_description = form.domain_description || null;
  return values;
}
