import { useCallback } from 'react';

import { useApiMutation } from './useApiMutation';
import { useApplicationAccountQuery } from './useApplicationAccountQuery';
import type {
  MCPBehaviorCandidates,
  MCPBehaviorPreview,
  MCPServerBehavior,
  MCPStrategyPreview,
  MCPToolChoice,
  MCPToolConfirmationRequest,
} from '@/lib/mcp-behavior';

const ENDPOINT = '/mcp/servers';

/**
 * What a saved server will do — the API's synthesis (spec 2026-10-30 D5).
 *
 * Read only while a server is shown; the page never computes a confirmation itself.
 */
export function useMCPServerBehavior(serverId: string | null) {
  const query = useApplicationAccountQuery<MCPServerBehavior>(
    `${ENDPOINT}/${serverId ?? ''}/behavior`,
    'MCPServerBehavior',
    serverId !== null
  );
  return {
    behavior: query.data,
    loading: query.loading,
    error: query.error,
    refetch: query.refetch,
  };
}

/**
 * The previews read before a change — they write nothing (spec 2026-10-30 § 6).
 *
 * `previewServer` answers the synthesis under the form's candidate values and the
 * questions it would remove; `previewStrategy` answers what a change of the account's
 * strategy would remove across its servers. An explicit null travels as null: it is
 * « back to the default », not « unchanged ».
 */
export function useMCPBehaviorPreview() {
  // A preview is read, never kept: `retainResponse: false` spares a render per answer.
  const { mutate: postServerPreview } = useApiMutation<MCPBehaviorCandidates, MCPBehaviorPreview>({
    method: 'POST',
    componentName: 'MCPBehaviorPreview',
    retainResponse: false,
  });
  const { mutate: postStrategyPreview } = useApiMutation<
    { mcp_hitl_required: boolean | null },
    MCPStrategyPreview
  >({ method: 'POST', componentName: 'MCPBehaviorPreview', retainResponse: false });

  // Stable across renders (`mutate` is): the live synthesis depends on them.
  const previewServer = useCallback(
    (serverId: string, candidates: MCPBehaviorCandidates) =>
      postServerPreview(`${ENDPOINT}/${serverId}/behavior/preview`, candidates),
    [postServerPreview]
  );
  const previewStrategy = useCallback(
    (value: boolean | null) =>
      postStrategyPreview(`${ENDPOINT}/strategy/preview`, { mcp_hitl_required: value }),
    [postStrategyPreview]
  );
  return { previewServer, previewStrategy };
}

/**
 * One tool's choice, written alone (spec 2026-10-30 D6): two tools changed in two
 * tabs never overwrite each other. Answers with the server's new synthesis. An
 * explicit null returns the tool to the levels below.
 */
export function useMCPToolChoice() {
  const { mutate: putToolChoice } = useApiMutation<MCPToolConfirmationRequest, MCPServerBehavior>({
    method: 'PUT',
    componentName: 'MCPToolChoice',
    retainResponse: false,
  });
  const setToolChoice = useCallback(
    (serverId: string, toolName: string, choice: MCPToolChoice | null) =>
      putToolChoice(`${ENDPOINT}/${serverId}/tool-confirmations`, { tool_name: toolName, choice }),
    [putToolChoice]
  );
  return { setToolChoice };
}
