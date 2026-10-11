# LIA application interface source inventory

**Snapshot:** 2026-10-06. **Method:** static source inspection; no server imports, network calls or database reads.

This appendix supports the [design](2026-10-06-lia-application-tools-design.md) and [implementation plan](../plans/2026-10-06-lia-application-tools.md).
The [machine-readable inventory](2026-10-06-lia-application-interface-inventory.json) contains endpoint signatures, source calls, frontend endpoint literals and source fingerprints.

Route counts below include declarations, conditional mounts and transport/internal endpoints. They are not a claim that every route is a user-facing capability or is enabled on an instance. Frontend endpoint literals are lexical evidence, not a runtime reachability proof. The design selects business operations, not every HTTP route.

**Scope decision — 2026-10-08:** New tools or secure forms for account passwords, MFA, passkeys, account recovery and telephone verification are explicitly excluded by the user. Their source declarations remain in this historical inventory as evidence, but are not pending implementation or required operation coverage. Existing authentication and confirmation safeguards needed by other included operations remain in force.

Measured declarations: **67 settings sections** (28 preferences, 21 features, 18 administration); **574 route declarations** in the scanned backend source.

## Every declared settings section

| Token | UI block | Source component | Imported hooks | Direct endpoint literals |
|---|---|---|---|---|
| `language` | preferences | [components/settings/LanguageSettings.tsx](../../../apps/web/src/components/settings/LanguageSettings.tsx) | useApiMutation, useAuth | /users/${user.id} |
| `timezone` | preferences | [components/settings/TimezoneSelector.tsx](../../../apps/web/src/components/settings/TimezoneSelector.tsx) | useApiMutation, useAuth | /users/${user.id}, /users/timezones |
| `location` | preferences | [components/settings/LocationSettings.tsx](../../../apps/web/src/components/settings/LocationSettings.tsx) | useApiMutation, useApiQuery, useGeolocation | /users/me/home-location |
| `theme` | preferences | [components/theme-selector.tsx](../../../apps/web/src/components/theme-selector.tsx) | useApiMutation, useAuth | /users/${user.id} |
| `font` | preferences | [components/settings/FontSettings.tsx](../../../apps/web/src/components/settings/FontSettings.tsx) | useApiMutation, useAuth | /users/${user.id} |
| `font-size` | preferences | [components/settings/FontSizeSettings.tsx](../../../apps/web/src/components/settings/FontSizeSettings.tsx) | useAuth, useFontSizeSave | Through imported hooks or client stores |
| `eyes-style` | preferences | [components/settings/EyesStyleSettings.tsx](../../../apps/web/src/components/settings/EyesStyleSettings.tsx) | See component imports | Through imported hooks or client stores |
| `display-mode` | preferences | [components/settings/CardsDisplaySettings.tsx](../../../apps/web/src/components/settings/CardsDisplaySettings.tsx) | useAuth | /auth/me/display-mode-preference |
| `usage-preferences` | preferences | [components/settings/UsagePreferencesSettings.tsx](../../../apps/web/src/components/settings/UsagePreferencesSettings.tsx) | useAuth | /users/${user.id} |
| `haptics` | preferences | [components/settings/HapticsSettings.tsx](../../../apps/web/src/components/settings/HapticsSettings.tsx) | See component imports | Through imported hooks or client stores |
| `briefing-grid` | preferences | [components/settings/BriefingGridSettings.tsx](../../../apps/web/src/components/settings/BriefingGridSettings.tsx) | useBriefingPreferences | Through imported hooks or client stores |
| `chat-shortcuts` | preferences | [components/settings/ChatShortcutsSettings.tsx](../../../apps/web/src/components/settings/ChatShortcutsSettings.tsx) | useChatShortcuts | Through imported hooks or client stores |
| `my-shortcuts` | preferences | [components/settings/MyShortcutsSettings.tsx](../../../apps/web/src/components/settings/MyShortcutsSettings.tsx) | useSettingsAvailability, useSettingsShortcuts | Through imported hooks or client stores |
| `notifications` | preferences | [components/settings/NotificationSettings.tsx](../../../apps/web/src/components/settings/NotificationSettings.tsx) | useFCMToken | Through imported hooks or client stores |
| `channels` | preferences | [components/settings/ChannelSettings.tsx](../../../apps/web/src/components/settings/ChannelSettings.tsx) | useChannelBindings | Through imported hooks or client stores |
| `security-auth` | preferences | [components/settings/SecuritySettings.tsx](../../../apps/web/src/components/settings/SecuritySettings.tsx) | useStepUpGuard, useWebAuthn | Through imported hooks or client stores |
| `security-devices` | preferences | [components/settings/DeviceSessionsSettings.tsx](../../../apps/web/src/components/settings/DeviceSessionsSettings.tsx) | useAuth, useSessions, useStepUpGuard | Through imported hooks or client stores |
| `security-export` | preferences | [components/settings/AccountExportSettings.tsx](../../../apps/web/src/components/settings/AccountExportSettings.tsx) | useApiQuery, useStepUpGuard | Through imported hooks or client stores |
| `voice-mode` | preferences | [components/settings/VoiceModeSettings.tsx](../../../apps/web/src/components/settings/VoiceModeSettings.tsx) | useAuth | /auth/me/voice-mode-preference |
| `live-mode` | preferences | [components/settings/LiveModeSettings.tsx](../../../apps/web/src/components/settings/LiveModeSettings.tsx) | useAppConfig, useLiveConnectorDraft, useLiveConnectorSettings, useLivePreferences, useVoiceSample | Through imported hooks or client stores |
| `avatar` | preferences | [components/settings/AvatarSettings.tsx](../../../apps/web/src/components/settings/AvatarSettings.tsx) | useApiQuery, useAppConfig, useAuth | /avatars/config, /avatars/faces, /avatars/settings |
| `radio` | preferences | [components/radio/settings/RadioSettings.tsx](../../../apps/web/src/components/radio/settings/RadioSettings.tsx) | See component imports | Through imported hooks or client stores |
| `image-generation` | preferences | [components/settings/ImageGenerationSettings.tsx](../../../apps/web/src/components/settings/ImageGenerationSettings.tsx) | useAuth, useImageGenerationOptions | /users/${user.id} |
| `generated-assets` | preferences | [components/settings/GeneratedAssetsSettings.tsx](../../../apps/web/src/components/settings/GeneratedAssetsSettings.tsx) | useApiMutation, useAppConfig, useGeneratedAssets, useMediaQuery | /generated-assets/delete, /generated-assets/keep |
| `connectors` | preferences | [components/settings/UserConnectorsSection.tsx](../../../apps/web/src/components/settings/UserConnectorsSection.tsx) | useApiMutation, useApiQuery, useBulkReconnect | /connectors, /connectors/${connectorId}, /connectors/api-key/activate |
| `telephony-calls` | preferences | [components/settings/TelephonyCallsSection.tsx](../../../apps/web/src/components/settings/TelephonyCallsSection.tsx) | useTelephonyCalls | Through imported hooks or client stores |
| `telephony-identity` | preferences | [components/settings/TelephonyIdentitySection.tsx](../../../apps/web/src/components/settings/TelephonyIdentitySection.tsx) | useTelephonyIdentity | Through imported hooks or client stores |
| `debug-panel` | preferences | [components/settings/UserDebugSettings.tsx](../../../apps/web/src/components/settings/UserDebugSettings.tsx) | useAuth | /auth/me/debug-panel-preference |
| `personality` | features | [components/settings/PersonalitySettings.tsx](../../../apps/web/src/components/settings/PersonalitySettings.tsx) | usePersonality | Through imported hooks or client stores |
| `psyche` | features | [components/settings/PsycheSettings.tsx](../../../apps/web/src/components/settings/PsycheSettings.tsx) | usePsyche | Through imported hooks or client stores |
| `memories` | features | [components/settings/MemorySettings.tsx](../../../apps/web/src/components/settings/MemorySettings.tsx) | useAuth, useMemories | /auth/me/memory-preference, /memories/${memory.id}/provenance, /memories/export |
| `interests` | features | [components/settings/InterestsSettings.tsx](../../../apps/web/src/components/settings/InterestsSettings.tsx) | useInterestNotificationHistory, useInterests | /interests/export |
| `open-loops` | features | [components/settings/OpenLoopsSection.tsx](../../../apps/web/src/components/settings/OpenLoopsSection.tsx) | useAppConfig, useOpenLoops | Through imported hooks or client stores |
| `habits` | features | [components/settings/HabitsSettings.tsx](../../../apps/web/src/components/settings/HabitsSettings.tsx) | useAppConfig, useHabits | Through imported hooks or client stores |
| `peer-connections` | features | [components/settings/PeerConnectionsSettings.tsx](../../../apps/web/src/components/settings/PeerConnectionsSettings.tsx) | useAppConfig, useAuth, usePeerConnections | Through imported hooks or client stores |
| `heartbeat` | features | [components/settings/HeartbeatSettings.tsx](../../../apps/web/src/components/settings/HeartbeatSettings.tsx) | useHeartbeatHistory, useHeartbeatSettings | Through imported hooks or client stores |
| `scheduled-actions` | features | [components/settings/ScheduledActionsSettings.tsx](../../../apps/web/src/components/settings/ScheduledActionsSettings.tsx) | useScheduledActions | Through imported hooks or client stores |
| `reminders` | features | [components/settings/RemindersSettings.tsx](../../../apps/web/src/components/settings/RemindersSettings.tsx) | useReminders | Through imported hooks or client stores |
| `journals` | features | [components/settings/JournalsSettings.tsx](../../../apps/web/src/components/settings/JournalsSettings.tsx) | useJournals | /journals/${entry.id}/provenance, /journals/export?format=${format} |
| `health-metrics` | features | [components/settings/HealthMetricsSettings.tsx](../../../apps/web/src/components/settings/HealthMetricsSettings.tsx) | useAuth, useHealthMetrics | /api/v1, /api/v1/ingest/health/heart_rate, /api/v1/ingest/health/steps |
| `skills` | features | [components/settings/SkillsSettings.tsx](../../../apps/web/src/components/settings/SkillsSettings.tsx) | useAppConfig, usePlugins, useSkills | Through imported hooks or client stores |
| `plugins` | features | [components/settings/PluginsSettings.tsx](../../../apps/web/src/components/settings/PluginsSettings.tsx) | usePlugins | Through imported hooks or client stores |
| `admin-mcp-servers` | features | [components/settings/AdminMCPServersSettings.tsx](../../../apps/web/src/components/settings/AdminMCPServersSettings.tsx) | useAdminMCPServers | Through imported hooks or client stores |
| `mcp-servers` | features | [components/settings/MCPServersSettings.tsx](../../../apps/web/src/components/settings/MCPServersSettings.tsx) | useUserMCPServers | Through imported hooks or client stores |
| `sandbox-egress` | features | [components/settings/SandboxEgressSettings.tsx](../../../apps/web/src/components/settings/SandboxEgressSettings.tsx) | useAppConfig, useSandboxEgress | Through imported hooks or client stores |
| `rag-spaces` | features | [components/spaces/SpacesSettingsSection.tsx](../../../apps/web/src/components/spaces/SpacesSettingsSection.tsx) | See component imports | Through imported hooks or client stores |
| `meetings` | features | [components/settings/MeetingsSettings.tsx](../../../apps/web/src/components/settings/MeetingsSettings.tsx) | useAppConfig, useLocalizedRouter, useMeetingPreferences, useMeetingTemplates, useMeetings | Through imported hooks or client stores |
| `workboard` | features | [components/settings/WorkboardSettings.tsx](../../../apps/web/src/components/settings/WorkboardSettings.tsx) | useAppConfig, useAuth, useLocalizedRouter, useWorkboardSummary | Through imported hooks or client stores |
| `user-consumption-export` | features | [components/settings/ConsumptionExportSection.tsx](../../../apps/web/src/components/settings/ConsumptionExportSection.tsx) | See component imports | /api/v1/admin/google-api/export, /api/v1/usage/export |
| `admin-users` | administration | [components/settings/AdminUsersSection.tsx](../../../apps/web/src/components/settings/AdminUsersSection.tsx) | See component imports | /users/admin/search |
| `admin-usage-limits` | administration | [components/settings/AdminUsageLimitsSection.tsx](../../../apps/web/src/components/settings/AdminUsageLimitsSection.tsx) | See component imports | /usage-limits/admin/users, /usage-limits/admin/users/${user.user_id}/block |
| `admin-consumption-export` | administration | [components/settings/AdminConsumptionExportSection.tsx](../../../apps/web/src/components/settings/AdminConsumptionExportSection.tsx) | See component imports | Through imported hooks or client stores |
| `admin-broadcast` | administration | [components/settings/AdminBroadcastSection.tsx](../../../apps/web/src/components/settings/AdminBroadcastSection.tsx) | useApiMutation, useApiQuery, useDebounce | /notifications/admin/broadcast, /users/admin/autocomplete?q=${encodeURIComponent(debouncedSearch)} |
| `admin-connectors` | administration | [components/settings/AdminConnectorsSection.tsx](../../../apps/web/src/components/settings/AdminConnectorsSection.tsx) | useApiMutation, useApiQuery | /connectors/admin/global-config |
| `admin-llm-pricing` | administration | [components/settings/AdminLLMPricingSection.tsx](../../../apps/web/src/components/settings/AdminLLMPricingSection.tsx) | useLLMPricingSheet | /admin/llm/catalogue-status, /admin/llm/pricing, /admin/llm/pricing?${params.toString()}, /admin/llm/reasoning-family?${query.toString()} |
| `admin-google-api-pricing` | administration | [components/settings/AdminGoogleApiPricingSection.tsx](../../../apps/web/src/components/settings/AdminGoogleApiPricingSection.tsx) | See component imports | /admin/google-api/pricing, /admin/google-api/pricing?${params.toString()} |
| `admin-image-pricing` | administration | [components/settings/AdminImagePricingSection.tsx](../../../apps/web/src/components/settings/AdminImagePricingSection.tsx) | See component imports | /admin/image-pricing/pricing?${params.toString()} |
| `admin-llm-config` | administration | [components/settings/AdminLLMConfigSection.tsx](../../../apps/web/src/components/settings/AdminLLMConfigSection.tsx) | useApiQuery, useLLMConfig | /admin/llm-config/providers/ollama/models, /admin/voice/voices?provider=${ttsProvider |
| `admin-jev` | administration | [components/settings/AdminJevSection.tsx](../../../apps/web/src/components/settings/AdminJevSection.tsx) | useApiMutation, useApiQuery | /admin/llm-config/jev |
| `admin-personalities` | administration | [components/settings/AdminPersonalitiesSection.tsx](../../../apps/web/src/components/settings/AdminPersonalitiesSection.tsx) | See component imports | Through imported hooks or client stores |
| `admin-skills` | administration | [components/settings/AdminSkillsSection.tsx](../../../apps/web/src/components/settings/AdminSkillsSection.tsx) | useSkills | Through imported hooks or client stores |
| `rag-spaces-admin` | administration | [components/settings/AdminRAGSpacesSection.tsx](../../../apps/web/src/components/settings/AdminRAGSpacesSection.tsx) | useApiMutation, useAppConfig | /rag-spaces/admin/reindex, /rag-spaces/admin/reindex/status, /rag-spaces/admin/system-spaces, /rag-spaces/admin/system-spaces/${name}/reindex, /rag-spaces/admin/system-spaces/${name}/staleness |
| `admin-capabilities` | administration | [components/settings/AdminCapabilitiesSection.tsx](../../../apps/web/src/components/settings/AdminCapabilitiesSection.tsx) | useApiMutation, useApiQuery | /admin/capabilities |
| `admin-public-demo-link` | administration | [components/settings/AdminPublicDemoLinkSection.tsx](../../../apps/web/src/components/settings/AdminPublicDemoLinkSection.tsx) | useApiMutation, useApiQuery | /admin/public-demo-link |
| `admin-registers` | administration | [components/settings/AdminRegistersSection.tsx](../../../apps/web/src/components/settings/AdminRegistersSection.tsx) | See component imports | /admin/effects/export, /admin/effects/export/article12${query, /admin/effects/export/readable |
| `admin-diagnostics` | administration | [components/settings/AdminDiagnosticsSection.tsx](../../../apps/web/src/components/settings/AdminDiagnosticsSection.tsx) | useDiagnostics | Through imported hooks or client stores |
| `debug-settings` | administration | [components/settings/AdminDebugSettingsSection.tsx](../../../apps/web/src/components/settings/AdminDebugSettingsSection.tsx) | useApiMutation, useApiQuery | /admin/system-settings/debug-panel, /admin/system-settings/debug-panel-user-access |

## Authenticated application pages

| Page source | Direct endpoint literals | Imported hooks |
|---|---|---|
| [apps/web/src/app/[lng]/dashboard/actions/page.tsx](../../../apps/web/src/app/[lng]/dashboard/actions/page.tsx) |  | @/hooks/useLanguageParam |
| [apps/web/src/app/[lng]/dashboard/activity/page.tsx](../../../apps/web/src/app/[lng]/dashboard/activity/page.tsx) |  | @/hooks/useLanguageParam |
| [apps/web/src/app/[lng]/dashboard/capabilities/page.tsx](../../../apps/web/src/app/[lng]/dashboard/capabilities/page.tsx) |  | @/hooks/useLanguageParam |
| [apps/web/src/app/[lng]/dashboard/chat/page.tsx](../../../apps/web/src/app/[lng]/dashboard/chat/page.tsx) |  | @/hooks/useAppConfig, @/hooks/useAuth, @/hooks/useAutoSendIntent, @/hooks/useCardComposition, @/hooks/useChat, @/hooks/useChatHistorySearch, @/hooks/useChatServerSync, @/hooks/useChatShortcuts, @/hooks/useChatSuggestions, @/hooks/useConversation, @/hooks/useDebugPanelEnabled, @/hooks/useDeepLinkParams, @/hooks/useInputDraft, @/hooks/useLiveSession, @/hooks/useLiveTabTitle, @/hooks/useLocalizedRouter, @/hooks/useSkills, @/hooks/useUsageLimits |
| [apps/web/src/app/[lng]/dashboard/design-system/cards/page.tsx](../../../apps/web/src/app/[lng]/dashboard/design-system/cards/page.tsx) |  |  |
| [apps/web/src/app/[lng]/dashboard/documents/[id]/page.tsx](../../../apps/web/src/app/[lng]/dashboard/documents/[id]/page.tsx) |  |  |
| [apps/web/src/app/[lng]/dashboard/faq/page.tsx](../../../apps/web/src/app/[lng]/dashboard/faq/page.tsx) |  |  |
| [apps/web/src/app/[lng]/dashboard/meetings/[id]/page.tsx](../../../apps/web/src/app/[lng]/dashboard/meetings/[id]/page.tsx) |  | @/hooks/useBackOrigin, @/hooks/useLanguageParam, @/hooks/useLocalizedRouter, @/hooks/useMeetings |
| [apps/web/src/app/[lng]/dashboard/meetings/page.tsx](../../../apps/web/src/app/[lng]/dashboard/meetings/page.tsx) |  | @/hooks/useBackOrigin, @/hooks/useLanguageParam, @/hooks/useLocalizedRouter, @/hooks/useMeetings |
| [apps/web/src/app/[lng]/dashboard/meetings/templates/page.tsx](../../../apps/web/src/app/[lng]/dashboard/meetings/templates/page.tsx) |  | @/hooks/useBackOrigin, @/hooks/useLanguageParam, @/hooks/useLocalizedRouter, @/hooks/useMeetingTemplates |
| [apps/web/src/app/[lng]/dashboard/notifications/page.tsx](../../../apps/web/src/app/[lng]/dashboard/notifications/page.tsx) |  | @/hooks/useLanguageParam |
| [apps/web/src/app/[lng]/dashboard/page.tsx](../../../apps/web/src/app/[lng]/dashboard/page.tsx) |  | @/hooks/useAppConfig, @/hooks/useAuth, @/hooks/useLanguageParam, @/hooks/usePersonalResults |
| [apps/web/src/app/[lng]/dashboard/radio/page.tsx](../../../apps/web/src/app/[lng]/dashboard/radio/page.tsx) |  | @/hooks/useAppConfig, @/hooks/useLanguageParam |
| [apps/web/src/app/[lng]/dashboard/relations/page.tsx](../../../apps/web/src/app/[lng]/dashboard/relations/page.tsx) |  | @/hooks/useLanguageParam, @/hooks/useRelations |
| [apps/web/src/app/[lng]/dashboard/settings/page.tsx](../../../apps/web/src/app/[lng]/dashboard/settings/page.tsx) |  | @/hooks/useAuth, @/hooks/useLanguageParam, @/hooks/useSettingsAvailability |
| [apps/web/src/app/[lng]/dashboard/spaces/[id]/page.tsx](../../../apps/web/src/app/[lng]/dashboard/spaces/[id]/page.tsx) | /rag-spaces/${spaceId}, /rag-spaces/${spaceId}/toggle | @/hooks/useApiMutation, @/hooks/useLocalizedRouter, @/hooks/useSpaceDocuments, @/hooks/useSpaceSources, @/hooks/useSpaces |
| [apps/web/src/app/[lng]/dashboard/spaces/page.tsx](../../../apps/web/src/app/[lng]/dashboard/spaces/page.tsx) |  |  |
| [apps/web/src/app/[lng]/dashboard/workboard/[id]/page.tsx](../../../apps/web/src/app/[lng]/dashboard/workboard/[id]/page.tsx) |  |  |
| [apps/web/src/app/[lng]/dashboard/workboard/page.tsx](../../../apps/web/src/app/[lng]/dashboard/workboard/page.tsx) |  |  |

## Declared backend routes by domain

An endpoint's signature and dependency calls are in the JSON appendix. Prefix expressions are retained as source text. Authentication, feature flags, ownership and side effects still have to be read through the handler and its service; a path name does not decide authority.

### account_export

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/account/export' + ''` | `request_export` | [apps/api/src/domains/account_export/router.py](../../../apps/api/src/domains/account_export/router.py) (line 72) |
| GET | `'/account/export' + '/latest'` | `latest_export` | [apps/api/src/domains/account_export/router.py](../../../apps/api/src/domains/account_export/router.py) (line 110) |
| GET | `'/account/export' + '/{job_id}/download'` | `download_export` | [apps/api/src/domains/account_export/router.py](../../../apps/api/src/domains/account_export/router.py) (line 132) |

### activity

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/activity' + '/timeline'` | `get_activity_timeline` | [apps/api/src/domains/activity/router.py](../../../apps/api/src/domains/activity/router.py) (line 26) |

### agents

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/agents' + '/chat/stream'` | `stream_chat` | [apps/api/src/domains/agents/api/router.py](../../../apps/api/src/domains/agents/api/router.py) (line 343) |
| GET | `'/agents' + '/runs/active'` | `get_active_run_status` | [apps/api/src/domains/agents/api/router.py](../../../apps/api/src/domains/agents/api/router.py) (line 1018) |
| GET | `'/agents' + '/hitl/pending'` | `get_pending_hitl_interrupt` | [apps/api/src/domains/agents/api/router.py](../../../apps/api/src/domains/agents/api/router.py) (line 1053) |
| POST | `'/agents' + '/runs/active/cancel'` | `cancel_active_run` | [apps/api/src/domains/agents/api/router.py](../../../apps/api/src/domains/agents/api/router.py) (line 1090) |
| GET | `'/agents' + '/runs/{stream_id}/stream'` | `reattach_run_stream` | [apps/api/src/domains/agents/api/router.py](../../../apps/api/src/domains/agents/api/router.py) (line 1139) |
| GET | `'/agents' + '/health'` | `agents_health` | [apps/api/src/domains/agents/api/router.py](../../../apps/api/src/domains/agents/api/router.py) (line 1200) |
| GET | `'/admin/effects' + '/export'` | `export_technical` | [apps/api/src/domains/agents/effects/admin_router.py](../../../apps/api/src/domains/agents/effects/admin_router.py) (line 100) |
| GET | `'/admin/effects' + '/readable'` | `read_admin_view` | [apps/api/src/domains/agents/effects/admin_router.py](../../../apps/api/src/domains/agents/effects/admin_router.py) (line 192) |
| GET | `'/admin/effects' + '/export/article12'` | `export_article12` | [apps/api/src/domains/agents/effects/admin_router.py](../../../apps/api/src/domains/agents/effects/admin_router.py) (line 495) |
| GET | `'/admin/effects' + '/export/readable'` | `export_readable_admin` | [apps/api/src/domains/agents/effects/admin_router.py](../../../apps/api/src/domains/agents/effects/admin_router.py) (line 574) |
| GET | `'/effects/chain' + '/status'` | `own_chain_seal` | [apps/api/src/domains/agents/effects/chain_router.py](../../../apps/api/src/domains/agents/effects/chain_router.py) (line 183) |
| GET | `'/effects/chain' + '/verify'` | `verify_own_chain` | [apps/api/src/domains/agents/effects/chain_router.py](../../../apps/api/src/domains/agents/effects/chain_router.py) (line 216) |
| GET | `'/admin/effects/chain' + '/verify'` | `verify_chains` | [apps/api/src/domains/agents/effects/chain_router.py](../../../apps/api/src/domains/agents/effects/chain_router.py) (line 241) |
| GET | `'/effects/export' + ''` | `export_register` | [apps/api/src/domains/agents/effects/export_router.py](../../../apps/api/src/domains/agents/effects/export_router.py) (line 178) |
| GET | `'/effects/export' + '/article12'` | `export_article12` | [apps/api/src/domains/agents/effects/export_router.py](../../../apps/api/src/domains/agents/effects/export_router.py) (line 307) |
| GET | `'/effects' + '/run/{run_id}'` | `list_run_effects` | [apps/api/src/domains/agents/effects/router.py](../../../apps/api/src/domains/agents/effects/router.py) (line 136) |
| GET | `'/effects' + '/journal'` | `list_journal` | [apps/api/src/domains/agents/effects/router.py](../../../apps/api/src/domains/agents/effects/router.py) (line 165) |
| GET | `'/effects/statistics' + ''` | `own_statistics` | [apps/api/src/domains/agents/effects/statistics_router.py](../../../apps/api/src/domains/agents/effects/statistics_router.py) (line 125) |
| GET | `'/admin/effects/statistics' + ''` | `admin_statistics` | [apps/api/src/domains/agents/effects/statistics_router.py](../../../apps/api/src/domains/agents/effects/statistics_router.py) (line 151) |
| GET | `'/effects/treatments' + '/run/{run_id}'` | `list_run_treatments` | [apps/api/src/domains/agents/effects/treatments_router.py](../../../apps/api/src/domains/agents/effects/treatments_router.py) (line 120) |
| GET | `'/effects/treatments' + '/journal'` | `list_treatment_journal` | [apps/api/src/domains/agents/effects/treatments_router.py](../../../apps/api/src/domains/agents/effects/treatments_router.py) (line 149) |
| GET | `'/sandbox/egress-grants' + ''` | `list_grants` | [apps/api/src/domains/agents/python_sandbox/egress/router.py](../../../apps/api/src/domains/agents/python_sandbox/egress/router.py) (line 63) |
| POST | `'/sandbox/egress-grants' + ''` | `add_grant` | [apps/api/src/domains/agents/python_sandbox/egress/router.py](../../../apps/api/src/domains/agents/python_sandbox/egress/router.py) (line 101) |
| GET | `'/sandbox/egress-grants' + '/reachable'` | `reachable_hosts` | [apps/api/src/domains/agents/python_sandbox/egress/router.py](../../../apps/api/src/domains/agents/python_sandbox/egress/router.py) (line 131) |
| PATCH | `'/sandbox/egress-grants' + '/{grant_id}'` | `update_grant_scope` | [apps/api/src/domains/agents/python_sandbox/egress/router.py](../../../apps/api/src/domains/agents/python_sandbox/egress/router.py) (line 156) |
| DELETE | `'/sandbox/egress-grants' + '/{grant_id}'` | `revoke_grant` | [apps/api/src/domains/agents/python_sandbox/egress/router.py](../../../apps/api/src/domains/agents/python_sandbox/egress/router.py) (line 173) |
| POST | `'/telephony/tools' + f'/{LIVE_DELEGATION_TOOL_NAME}'` | `delegation_callback` | [apps/api/src/domains/agents/telephony/live_tools_router.py](../../../apps/api/src/domains/agents/telephony/live_tools_router.py) (line 153) |
| POST | `'/telephony/tools' + '/{tool_name}'` | `live_tool_callback` | [apps/api/src/domains/agents/telephony/live_tools_router.py](../../../apps/api/src/domains/agents/telephony/live_tools_router.py) (line 235) |

### attachments

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/generated-assets' + ''` | `list_generated_assets` | [apps/api/src/domains/attachments/gallery_router.py](../../../apps/api/src/domains/attachments/gallery_router.py) (line 63) |
| POST | `'/generated-assets' + '/keep'` | `keep_generated_assets` | [apps/api/src/domains/attachments/gallery_router.py](../../../apps/api/src/domains/attachments/gallery_router.py) (line 134) |
| DELETE | `'/generated-assets' + '/{asset_id}'` | `delete_generated_asset` | [apps/api/src/domains/attachments/gallery_router.py](../../../apps/api/src/domains/attachments/gallery_router.py) (line 169) |
| POST | `'/generated-assets' + '/delete'` | `delete_generated_assets` | [apps/api/src/domains/attachments/gallery_router.py](../../../apps/api/src/domains/attachments/gallery_router.py) (line 189) |
| POST | `'/attachments' + '/upload'` | `upload_attachment` | [apps/api/src/domains/attachments/router.py](../../../apps/api/src/domains/attachments/router.py) (line 56) |
| POST | `'/attachments' + '/from-knowledge-document'` | `attach_knowledge_document` | [apps/api/src/domains/attachments/router.py](../../../apps/api/src/domains/attachments/router.py) (line 90) |
| GET | `'/attachments' + '/{attachment_id}'` | `get_attachment` | [apps/api/src/domains/attachments/router.py](../../../apps/api/src/domains/attachments/router.py) (line 113) |
| GET | `'/attachments' + '/{attachment_id}/preview'` | `get_attachment_preview` | [apps/api/src/domains/attachments/router.py](../../../apps/api/src/domains/attachments/router.py) (line 159) |
| DELETE | `'/attachments' + '/{attachment_id}'` | `delete_attachment` | [apps/api/src/domains/attachments/router.py](../../../apps/api/src/domains/attachments/router.py) (line 199) |

### auth

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| PATCH | `'/auth' + '/me/onboarding-checklist'` | `update_onboarding_checklist` | [apps/api/src/domains/auth/checklist_router.py](../../../apps/api/src/domains/auth/checklist_router.py) (line 39) |
| GET | `'/auth' + '/google/login'` | `google_login` | [apps/api/src/domains/auth/oauth_router.py](../../../apps/api/src/domains/auth/oauth_router.py) (line 83) |
| GET | `'/auth' + '/google/callback'` | `google_callback` | [apps/api/src/domains/auth/oauth_router.py](../../../apps/api/src/domains/auth/oauth_router.py) (line 209) |
| POST | `'/auth' + '/native/callback'` | `native_callback` | [apps/api/src/domains/auth/oauth_router.py](../../../apps/api/src/domains/auth/oauth_router.py) (line 392) |
| GET | `'/auth' + '/profile-image-proxy'` | `proxy_profile_image` | [apps/api/src/domains/auth/profile_image_router.py](../../../apps/api/src/domains/auth/profile_image_router.py) (line 155) |
| GET | `'/auth' + '/features'` | `auth_features` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 114) |
| POST | `'/auth' + '/register'` | `register` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 138) |
| POST | `'/auth' + '/login'` | `login` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 201) |
| POST | `'/auth' + '/refresh'` | `refresh_token` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 320) |
| POST | `'/auth' + '/logout'` | `logout` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 376) |
| POST | `'/auth' + '/logout-all'` | `logout_all_devices` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 424) |
| GET | `'/auth' + '/me'` | `get_me` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 467) |
| PATCH | `'/auth' + '/me/memory-preference'` | `update_memory_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 500) |
| PATCH | `'/auth' + '/me/health-metrics-agents-preference'` | `update_health_metrics_agents_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 548) |
| PATCH | `'/auth' + '/me/execution-mode-preference'` | `update_execution_mode_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 594) |
| PATCH | `'/auth' + '/me/location-preference'` | `update_location_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 642) |
| PUT | `'/auth' + '/me/last-location'` | `put_last_location` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 691) |
| GET | `'/auth' + '/me/last-location'` | `get_last_location` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 735) |
| PATCH | `'/auth' + '/me/voice-preference'` | `update_voice_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 769) |
| GET | `'/auth' + '/me/voice-mode-preference'` | `get_voice_mode_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 834) |
| PATCH | `'/auth' + '/me/voice-mode-preference'` | `update_voice_mode_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 863) |
| PATCH | `'/auth' + '/me/tokens-display-preference'` | `update_tokens_display_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 928) |
| PATCH | `'/auth' + '/me/login-notifications-preference'` | `update_login_notifications_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 973) |
| PATCH | `'/auth' + '/me/onboarding-preference'` | `update_onboarding_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 1012) |
| PATCH | `'/auth' + '/me/debug-panel-preference'` | `update_debug_panel_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 1057) |
| PATCH | `'/auth' + '/me/display-mode-preference'` | `update_display_mode_preference` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 1108) |
| POST | `'/auth' + '/verify-email'` | `verify_email` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 1162) |
| POST | `'/auth' + '/request-password-reset'` | `request_password_reset` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 1177) |
| POST | `'/auth' + '/reset-password'` | `reset_password` | [apps/api/src/domains/auth/router.py](../../../apps/api/src/domains/auth/router.py) (line 1195) |
| GET | `'/auth/sessions' + ''` | `list_sessions` | [apps/api/src/domains/auth/sessions_router.py](../../../apps/api/src/domains/auth/sessions_router.py) (line 65) |
| DELETE | `'/auth/sessions' + '/{display_id}'` | `revoke_session` | [apps/api/src/domains/auth/sessions_router.py](../../../apps/api/src/domains/auth/sessions_router.py) (line 85) |
| POST | `'/auth/sessions' + '/revoke-others'` | `revoke_other_sessions` | [apps/api/src/domains/auth/sessions_router.py](../../../apps/api/src/domains/auth/sessions_router.py) (line 110) |
| GET | `'/auth' + '/step-up/status'` | `step_up_status` | [apps/api/src/domains/auth/step_up_router.py](../../../apps/api/src/domains/auth/step_up_router.py) (line 65) |
| POST | `'/auth' + '/step-up/password'` | `step_up_password` | [apps/api/src/domains/auth/step_up_router.py](../../../apps/api/src/domains/auth/step_up_router.py) (line 112) |
| POST | `'/auth' + '/step-up/totp'` | `step_up_totp` | [apps/api/src/domains/auth/step_up_router.py](../../../apps/api/src/domains/auth/step_up_router.py) (line 133) |
| POST | `'/auth' + '/step-up/webauthn/options'` | `step_up_webauthn_options` | [apps/api/src/domains/auth/step_up_router.py](../../../apps/api/src/domains/auth/step_up_router.py) (line 154) |
| POST | `'/auth' + '/step-up/webauthn/verify'` | `step_up_webauthn_verify` | [apps/api/src/domains/auth/step_up_router.py](../../../apps/api/src/domains/auth/step_up_router.py) (line 170) |
| POST | `'/auth' + '/password/disable'` | `disable_password` | [apps/api/src/domains/auth/step_up_router.py](../../../apps/api/src/domains/auth/step_up_router.py) (line 194) |
| POST | `'/auth' + '/totp/enroll'` | `totp_enroll` | [apps/api/src/domains/auth/totp_router.py](../../../apps/api/src/domains/auth/totp_router.py) (line 70) |
| POST | `'/auth' + '/totp/confirm'` | `totp_confirm` | [apps/api/src/domains/auth/totp_router.py](../../../apps/api/src/domains/auth/totp_router.py) (line 88) |
| GET | `'/auth' + '/totp/status'` | `totp_status` | [apps/api/src/domains/auth/totp_router.py](../../../apps/api/src/domains/auth/totp_router.py) (line 109) |
| DELETE | `'/auth' + '/totp'` | `totp_disable` | [apps/api/src/domains/auth/totp_router.py](../../../apps/api/src/domains/auth/totp_router.py) (line 129) |
| POST | `'/auth' + '/totp/backup-codes/regenerate'` | `totp_regenerate_backup_codes` | [apps/api/src/domains/auth/totp_router.py](../../../apps/api/src/domains/auth/totp_router.py) (line 145) |
| POST | `'/auth' + '/mfa/verify'` | `mfa_verify` | [apps/api/src/domains/auth/totp_router.py](../../../apps/api/src/domains/auth/totp_router.py) (line 166) |
| POST | `'/auth/webauthn' + '/register/options'` | `register_options` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 64) |
| POST | `'/auth/webauthn' + '/register/verify'` | `register_verify` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 82) |
| GET | `'/auth/webauthn' + '/credentials'` | `list_credentials` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 100) |
| PATCH | `'/auth/webauthn' + '/credentials/{row_id}'` | `rename_credential` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 116) |
| DELETE | `'/auth/webauthn' + '/credentials/{row_id}'` | `delete_credential` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 136) |
| POST | `'/auth/webauthn' + '/authenticate/options'` | `authenticate_options` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 154) |
| POST | `'/auth/webauthn' + '/authenticate/verify'` | `authenticate_verify` | [apps/api/src/domains/auth/webauthn_router.py](../../../apps/api/src/domains/auth/webauthn_router.py) (line 171) |

### avatars

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| WEBSOCKET | `'/avatars' + '/ws'` | `avatar_socket` | [apps/api/src/domains/avatars/relay.py](../../../apps/api/src/domains/avatars/relay.py) (line 161) |
| GET | `'/avatars' + '/config'` | `config` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 50) |
| PUT | `'/avatars' + '/settings'` | `save_settings` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 58) |
| GET | `'/avatars' + '/faces'` | `faces` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 68) |
| POST | `'/avatars' + '/sessions'` | `start` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 81) |
| POST | `'/avatars' + '/sessions/heartbeat'` | `heartbeat` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 90) |
| POST | `'/avatars' + '/sessions/release'` | `release` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 99) |
| GET | `'/avatars' + '/sessions/current'` | `current_session` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 108) |
| POST | `'/avatars' + '/sessions/failure'` | `failure_report` | [apps/api/src/domains/avatars/router.py](../../../apps/api/src/domains/avatars/router.py) (line 116) |

### bookmarks

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/bookmarks' + ''` | `keep_bookmark` | [apps/api/src/domains/bookmarks/router.py](../../../apps/api/src/domains/bookmarks/router.py) (line 53) |
| GET | `'/bookmarks' + ''` | `list_bookmarks` | [apps/api/src/domains/bookmarks/router.py](../../../apps/api/src/domains/bookmarks/router.py) (line 87) |
| GET | `'/bookmarks' + '/state'` | `bookmark_state` | [apps/api/src/domains/bookmarks/router.py](../../../apps/api/src/domains/bookmarks/router.py) (line 129) |
| DELETE | `'/bookmarks' + '/by-message/{message_id}'` | `remove_bookmark_by_message` | [apps/api/src/domains/bookmarks/router.py](../../../apps/api/src/domains/bookmarks/router.py) (line 152) |
| DELETE | `'/bookmarks' + '/{bookmark_id}'` | `remove_bookmark` | [apps/api/src/domains/bookmarks/router.py](../../../apps/api/src/domains/bookmarks/router.py) (line 176) |

### briefing

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/briefing' + '/companion-context'` | `get_companion_context` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 49) |
| GET | `'/briefing' + '/cards'` | `get_briefing_cards` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 82) |
| GET | `'/briefing' + '/synthesis'` | `get_briefing_synthesis` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 99) |
| POST | `'/briefing' + '/refresh-cards'` | `refresh_briefing_cards` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 116) |
| POST | `'/briefing' + '/refresh'` | `refresh_today_briefing` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 136) |
| GET | `'/briefing' + '/preferences'` | `get_briefing_preferences` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 157) |
| PUT | `'/briefing' + '/preferences'` | `put_briefing_preferences` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 173) |
| POST | `'/briefing' + '/synthesis/audio'` | `synthesis_audio` | [apps/api/src/domains/briefing/router.py](../../../apps/api/src/domains/briefing/router.py) (line 219) |

### capabilities

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/capabilities' + ''` | `get_capability_map` | [apps/api/src/domains/capabilities/router.py](../../../apps/api/src/domains/capabilities/router.py) (line 67) |

### channels

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/channels' + '/otp/generate'` | `generate_otp` | [apps/api/src/domains/channels/router.py](../../../apps/api/src/domains/channels/router.py) (line 87) |
| GET | `'/channels' + ''` | `list_bindings` | [apps/api/src/domains/channels/router.py](../../../apps/api/src/domains/channels/router.py) (line 125) |
| PATCH | `'/channels' + '/{binding_id}/toggle'` | `toggle_binding` | [apps/api/src/domains/channels/router.py](../../../apps/api/src/domains/channels/router.py) (line 151) |
| DELETE | `'/channels' + '/{binding_id}'` | `unlink_binding` | [apps/api/src/domains/channels/router.py](../../../apps/api/src/domains/channels/router.py) (line 176) |
| POST | `'/channels' + '/telegram/webhook'` | `telegram_webhook` | [apps/api/src/domains/channels/router.py](../../../apps/api/src/domains/channels/router.py) (line 203) |

### chat

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/chat' + '/shortcuts'` | `get_chat_shortcuts` | [apps/api/src/domains/chat/router.py](../../../apps/api/src/domains/chat/router.py) (line 34) |
| PUT | `'/chat' + '/shortcuts'` | `put_chat_shortcuts` | [apps/api/src/domains/chat/router.py](../../../apps/api/src/domains/chat/router.py) (line 54) |
| GET | `'/chat' + '/users/me/statistics'` | `get_user_statistics` | [apps/api/src/domains/chat/router.py](../../../apps/api/src/domains/chat/router.py) (line 83) |
| GET | `'/chat' + '/suggestions'` | `get_chat_suggestions` | [apps/api/src/domains/chat/router.py](../../../apps/api/src/domains/chat/router.py) (line 117) |

### connectors

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'' + '/google-maps/load-admissions'` | `admit_map_load` | [apps/api/src/domains/connectors/map_load_router.py](../../../apps/api/src/domains/connectors/map_load_router.py) (line 35) |
| POST | `'' + '/google-maps/load-reports'` | `report_map_load` | [apps/api/src/domains/connectors/map_load_router.py](../../../apps/api/src/domains/connectors/map_load_router.py) (line 46) |
| GET | `'' + '/google-routes/static-map'` | `proxy_routes_static_map` | [apps/api/src/domains/connectors/media_proxy_router.py](../../../apps/api/src/domains/connectors/media_proxy_router.py) (line 154) |
| GET | `'' + '/google-location/static-map'` | `proxy_location_static_map` | [apps/api/src/domains/connectors/media_proxy_router.py](../../../apps/api/src/domains/connectors/media_proxy_router.py) (line 303) |
| GET | `'' + '/street-view'` | `proxy_street_view` | [apps/api/src/domains/connectors/media_proxy_router.py](../../../apps/api/src/domains/connectors/media_proxy_router.py) (line 413) |
| POST | `'' + '/oauth-bulk/{provider}/connect-all/authorize'` | `initiate_bulk_oauth_connection` | [apps/api/src/domains/connectors/oauth_bulk_router.py](../../../apps/api/src/domains/connectors/oauth_bulk_router.py) (line 34) |
| POST | `'' + '/oauth-bulk/{provider}/authorize'` | `initiate_bulk_oauth_reconnection` | [apps/api/src/domains/connectors/oauth_bulk_router.py](../../../apps/api/src/domains/connectors/oauth_bulk_router.py) (line 54) |
| GET | `'' + '/oauth-bulk/{provider}/callback'` | `bulk_oauth_callback` | [apps/api/src/domains/connectors/oauth_bulk_router.py](../../../apps/api/src/domains/connectors/oauth_bulk_router.py) (line 70) |
| GET | `'/connectors' + ''` | `get_connectors` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 98) |
| GET | `'/connectors' + '/types'` | `list_connector_types` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 115) |
| GET | `'/connectors' + '/gmail/attachment/{message_id}/{attachment_id}'` | `proxy_gmail_attachment` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 157) |
| GET | `'/connectors' + '/health/settings'` | `get_health_settings` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 247) |
| GET | `'/connectors' + '/health'` | `check_connector_health` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 274) |
| GET | `'/connectors' + '/{connector_id}'` | `get_connector` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 296) |
| PATCH | `'/connectors' + '/{connector_id}'` | `update_connector` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 313) |
| DELETE | `'/connectors' + '/{connector_id}'` | `delete_connector` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 332) |
| POST | `'/connectors' + '/{connector_id}/refresh'` | `refresh_connector_credentials` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 350) |
| GET | `'/connectors' + '/{connector_id}/preferences'` | `get_connector_preferences` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 373) |
| PATCH | `'/connectors' + '/{connector_id}/preferences'` | `update_connector_preferences` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 422) |
| GET | `'/connectors' + '/{connector_id}/calendars'` | `list_connector_calendars` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 535) |
| GET | `'/connectors' + '/{connector_id}/task-lists'` | `list_connector_task_lists` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 593) |
| GET | `'/connectors' + '/gmail/authorize'` | `initiate_gmail_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 652) |
| GET | `'/connectors' + '/gmail/callback'` | `gmail_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 672) |
| GET | `'/connectors' + '/google-contacts/authorize'` | `initiate_google_contacts_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 715) |
| GET | `'/connectors' + '/google-contacts/callback'` | `google_contacts_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 735) |
| POST | `'/connectors' + '/google-contacts/activate'` | `activate_google_contacts_connector` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 786) |
| GET | `'/connectors' + '/google-calendar/authorize'` | `initiate_google_calendar_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 805) |
| GET | `'/connectors' + '/google-calendar/callback'` | `google_calendar_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 824) |
| GET | `'/connectors' + '/google-drive/authorize'` | `initiate_google_drive_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 862) |
| GET | `'/connectors' + '/google-drive/callback'` | `google_drive_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 881) |
| GET | `'/connectors' + '/google-tasks/authorize'` | `initiate_google_tasks_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 919) |
| GET | `'/connectors' + '/google-tasks/callback'` | `google_tasks_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 938) |
| GET | `'/connectors' + '/microsoft-outlook/authorize'` | `initiate_microsoft_outlook_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 976) |
| GET | `'/connectors' + '/microsoft-outlook/callback'` | `microsoft_outlook_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 991) |
| GET | `'/connectors' + '/microsoft-calendar/authorize'` | `initiate_microsoft_calendar_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1022) |
| GET | `'/connectors' + '/microsoft-calendar/callback'` | `microsoft_calendar_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1037) |
| GET | `'/connectors' + '/microsoft-contacts/authorize'` | `initiate_microsoft_contacts_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1068) |
| GET | `'/connectors' + '/microsoft-contacts/callback'` | `microsoft_contacts_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1083) |
| GET | `'/connectors' + '/microsoft-tasks/authorize'` | `initiate_microsoft_tasks_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1114) |
| GET | `'/connectors' + '/microsoft-tasks/callback'` | `microsoft_tasks_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1129) |
| GET | `'/connectors' + '/google-drive/thumbnail/{file_id}'` | `proxy_drive_thumbnail` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1166) |
| GET | `'/connectors' + '/google-places/photo/{photo_name:path}'` | `proxy_places_photo` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1260) |
| POST | `'/connectors' + '/api-key/activate'` | `activate_api_key_connector` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1392) |
| POST | `'/connectors' + '/api-key/validate'` | `validate_api_key` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1442) |
| GET | `'/connectors' + '/api-key/{connector_id}/info'` | `get_api_key_info` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1486) |
| PUT | `'/connectors' + '/api-key/{connector_id}/rotate'` | `rotate_api_key` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1544) |
| GET | `'/connectors' + '/admin/global-config'` | `get_all_connector_configs` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1589) |
| PUT | `'/connectors' + '/admin/global-config/{connector_type}'` | `update_connector_config` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1609) |
| POST | `'/connectors' + '/apple/validate'` | `validate_apple_connection` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1634) |
| POST | `'/connectors' + '/apple/activate'` | `activate_apple_connectors` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1666) |
| POST | `'/connectors' + '/philips-hue/discover'` | `discover_hue_bridges` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1695) |
| POST | `'/connectors' + '/philips-hue/pair'` | `pair_hue_bridge` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1721) |
| POST | `'/connectors' + '/philips-hue/activate/local'` | `activate_hue_local` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1777) |
| GET | `'/connectors' + '/philips-hue/authorize'` | `initiate_hue_oauth` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1802) |
| GET | `'/connectors' + '/philips-hue/callback'` | `hue_oauth_callback` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1816) |
| POST | `'/connectors' + '/philips-hue/test'` | `test_hue_connection` | [apps/api/src/domains/connectors/router.py](../../../apps/api/src/domains/connectors/router.py) (line 1858) |

### conversations

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/conversations' + '/me'` | `get_my_conversation` | [apps/api/src/domains/conversations/router.py](../../../apps/api/src/domains/conversations/router.py) (line 62) |
| GET | `'/conversations' + '/me/messages'` | `get_conversation_messages` | [apps/api/src/domains/conversations/router.py](../../../apps/api/src/domains/conversations/router.py) (line 98) |
| POST | `'/conversations' + '/me/messages/{message_id}/feedback'` | `submit_response_feedback` | [apps/api/src/domains/conversations/router.py](../../../apps/api/src/domains/conversations/router.py) (line 250) |
| POST | `'/conversations' + '/me/reset'` | `reset_my_conversation` | [apps/api/src/domains/conversations/router.py](../../../apps/api/src/domains/conversations/router.py) (line 336) |
| GET | `'/conversations' + '/me/stats'` | `get_conversation_stats` | [apps/api/src/domains/conversations/router.py](../../../apps/api/src/domains/conversations/router.py) (line 405) |
| GET | `'/conversations' + '/me/totals'` | `get_conversation_totals` | [apps/api/src/domains/conversations/router.py](../../../apps/api/src/domains/conversations/router.py) (line 449) |

### diagnostics

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/admin/diagnostics' + '/overview'` | `get_overview` | [apps/api/src/domains/diagnostics/router.py](../../../apps/api/src/domains/diagnostics/router.py) (line 46) |
| GET | `'/admin/diagnostics' + '/incidents'` | `list_incidents` | [apps/api/src/domains/diagnostics/router.py](../../../apps/api/src/domains/diagnostics/router.py) (line 61) |
| GET | `'/admin/diagnostics' + '/incidents/{incident_id}'` | `get_incident` | [apps/api/src/domains/diagnostics/router.py](../../../apps/api/src/domains/diagnostics/router.py) (line 100) |
| GET | `'/admin/diagnostics' + '/snapshots'` | `list_snapshots` | [apps/api/src/domains/diagnostics/router.py](../../../apps/api/src/domains/diagnostics/router.py) (line 135) |
| POST | `'/internal/diagnostics' + '/alert-webhook'` | `alert_webhook` | [apps/api/src/domains/diagnostics/webhook_router.py](../../../apps/api/src/domains/diagnostics/webhook_router.py) (line 44) |

### email_share

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/email-share' + '/options'` | `get_email_share_options` | [apps/api/src/domains/email_share/router.py](../../../apps/api/src/domains/email_share/router.py) (line 76) |
| GET | `'/email-share' + '/recipients'` | `get_recipient_suggestions` | [apps/api/src/domains/email_share/router.py](../../../apps/api/src/domains/email_share/router.py) (line 96) |
| POST | `'/email-share' + ''` | `send_by_email` | [apps/api/src/domains/email_share/router.py](../../../apps/api/src/domains/email_share/router.py) (line 126) |

### feature_switches

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/admin/capabilities' + ''` | `list_capability_switches` | [apps/api/src/domains/feature_switches/router.py](../../../apps/api/src/domains/feature_switches/router.py) (line 40) |
| PUT | `'/admin/capabilities' + '/{capability}'` | `update_capability_switch` | [apps/api/src/domains/feature_switches/router.py](../../../apps/api/src/domains/feature_switches/router.py) (line 59) |

### google_api

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/admin/google-api' + '/pricing'` | `list_active_pricing` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 47) |
| POST | `'/admin/google-api' + '/pricing'` | `create_pricing` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 157) |
| PUT | `'/admin/google-api' + '/pricing/{api_name}/{endpoint:path}'` | `update_pricing` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 229) |
| DELETE | `'/admin/google-api' + '/pricing/{pricing_id}'` | `deactivate_pricing` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 348) |
| POST | `'/admin/google-api' + '/pricing/reload-cache'` | `reload_pricing_cache` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 399) |
| GET | `'/admin/google-api' + '/export/token-usage'` | `export_token_usage` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 448) |
| GET | `'/admin/google-api' + '/export/google-api-usage'` | `export_google_api_usage` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 484) |
| GET | `'/admin/google-api' + '/export/consumption-summary'` | `export_consumption_summary` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 520) |
| GET | `'/admin/google-api' + '/export/stt-usage'` | `export_stt_usage` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 556) |
| GET | `'/admin/google-api' + '/export/tts-usage'` | `export_tts_usage` | [apps/api/src/domains/google_api/router.py](../../../apps/api/src/domains/google_api/router.py) (line 593) |
| GET | `'/usage/export' + '/token-usage'` | `user_export_token_usage` | [apps/api/src/domains/google_api/user_export_router.py](../../../apps/api/src/domains/google_api/user_export_router.py) (line 34) |
| GET | `'/usage/export' + '/google-api-usage'` | `user_export_google_api_usage` | [apps/api/src/domains/google_api/user_export_router.py](../../../apps/api/src/domains/google_api/user_export_router.py) (line 65) |
| GET | `'/usage/export' + '/consumption-summary'` | `user_export_consumption_summary` | [apps/api/src/domains/google_api/user_export_router.py](../../../apps/api/src/domains/google_api/user_export_router.py) (line 96) |
| GET | `'/usage/export' + '/stt-usage'` | `user_export_stt_usage` | [apps/api/src/domains/google_api/user_export_router.py](../../../apps/api/src/domains/google_api/user_export_router.py) (line 127) |
| GET | `'/usage/export' + '/tts-usage'` | `user_export_tts_usage` | [apps/api/src/domains/google_api/user_export_router.py](../../../apps/api/src/domains/google_api/user_export_router.py) (line 160) |

### habits

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/habits' + ''` | `get_habits_overview` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 129) |
| POST | `'/habits' + '/recompute'` | `recompute_habits_now` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 180) |
| POST | `'/habits' + '/presence'` | `record_reading_presence` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 208) |
| PATCH | `'/habits' + '/settings'` | `update_habits_settings` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 238) |
| GET | `'/habits' + '/{habit_id}/explanation'` | `get_habit_explanation` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 261) |
| POST | `'/habits' + '/{habit_id}/status'` | `set_habit_status` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 284) |
| DELETE | `'/habits' + '/{habit_id}'` | `delete_habit` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 312) |
| DELETE | `'/habits' + ''` | `delete_all_habits` | [apps/api/src/domains/habits/router.py](../../../apps/api/src/domains/habits/router.py) (line 333) |

### health_metrics

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/ingest/health' + '/steps'` | `ingest_steps` | [apps/api/src/domains/health_metrics/ingest_router.py](../../../apps/api/src/domains/health_metrics/ingest_router.py) (line 236) |
| POST | `'/ingest/health' + '/heart_rate'` | `ingest_heart_rate` | [apps/api/src/domains/health_metrics/ingest_router.py](../../../apps/api/src/domains/health_metrics/ingest_router.py) (line 261) |
| GET | `'/health-metrics' + ''` | `list_samples` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 55) |
| GET | `'/health-metrics' + '/aggregate'` | `aggregate_metrics_endpoint` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 81) |
| DELETE | `'/health-metrics' + '/all'` | `delete_all_samples` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 104) |
| DELETE | `'/health-metrics' + ''` | `delete_samples_by_kind` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 116) |
| GET | `'/health-metrics' + '/tokens'` | `list_tokens` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 143) |
| POST | `'/health-metrics' + '/tokens'` | `create_token` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 160) |
| DELETE | `'/health-metrics' + '/tokens/{token_id}'` | `revoke_token` | [apps/api/src/domains/health_metrics/router.py](../../../apps/api/src/domains/health_metrics/router.py) (line 176) |

### heartbeat

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/heartbeat' + '/settings'` | `get_heartbeat_settings` | [apps/api/src/domains/heartbeat/router.py](../../../apps/api/src/domains/heartbeat/router.py) (line 114) |
| PATCH | `'/heartbeat' + '/settings'` | `update_heartbeat_settings` | [apps/api/src/domains/heartbeat/router.py](../../../apps/api/src/domains/heartbeat/router.py) (line 130) |
| GET | `'/heartbeat' + '/history'` | `get_heartbeat_history` | [apps/api/src/domains/heartbeat/router.py](../../../apps/api/src/domains/heartbeat/router.py) (line 202) |
| GET | `'/heartbeat' + '/offers'` | `get_open_offers` | [apps/api/src/domains/heartbeat/router.py](../../../apps/api/src/domains/heartbeat/router.py) (line 228) |
| PATCH | `'/heartbeat' + '/notifications/{notification_id}/feedback'` | `submit_heartbeat_feedback` | [apps/api/src/domains/heartbeat/router.py](../../../apps/api/src/domains/heartbeat/router.py) (line 257) |

### image_generation

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/image-generation' + '/options'` | `get_image_generation_options` | [apps/api/src/domains/image_generation/options_router.py](../../../apps/api/src/domains/image_generation/options_router.py) (line 108) |
| GET | `'/admin/image-pricing' + '/pricing'` | `list_active_pricing` | [apps/api/src/domains/image_generation/router.py](../../../apps/api/src/domains/image_generation/router.py) (line 89) |
| POST | `'/admin/image-pricing' + '/pricing'` | `create_pricing` | [apps/api/src/domains/image_generation/router.py](../../../apps/api/src/domains/image_generation/router.py) (line 183) |
| PUT | `'/admin/image-pricing' + '/pricing/{pricing_id}'` | `update_pricing` | [apps/api/src/domains/image_generation/router.py](../../../apps/api/src/domains/image_generation/router.py) (line 287) |
| DELETE | `'/admin/image-pricing' + '/pricing/{pricing_id}'` | `deactivate_pricing` | [apps/api/src/domains/image_generation/router.py](../../../apps/api/src/domains/image_generation/router.py) (line 409) |
| POST | `'/admin/image-pricing' + '/pricing/reload-cache'` | `reload_pricing_cache` | [apps/api/src/domains/image_generation/router.py](../../../apps/api/src/domains/image_generation/router.py) (line 461) |

### interests

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/interests' + '/{interest_id}/explanation'` | `get_interest_explanation` | [apps/api/src/domains/interests/explainability_router.py](../../../apps/api/src/domains/interests/explainability_router.py) (line 60) |
| GET | `'/interests' + '/{interest_id}/provenance'` | `get_interest_provenance` | [apps/api/src/domains/interests/explainability_router.py](../../../apps/api/src/domains/interests/explainability_router.py) (line 118) |
| GET | `'/interests' + '/notifications/history'` | `get_interest_notification_history` | [apps/api/src/domains/interests/notifications_router.py](../../../apps/api/src/domains/interests/notifications_router.py) (line 38) |
| GET | `'/interests' + '/categories'` | `list_categories` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 122) |
| GET | `'/interests' + ''` | `list_interests` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 161) |
| POST | `'/interests' + ''` | `create_interest` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 216) |
| GET | `'/interests' + '/settings'` | `get_settings` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 302) |
| PATCH | `'/interests' + '/settings'` | `update_settings` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 315) |
| DELETE | `'/interests' + '/all'` | `delete_all_interests` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 368) |
| GET | `'/interests' + '/export'` | `export_interests` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 409) |
| DELETE | `'/interests' + '/{interest_id}'` | `delete_interest` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 494) |
| PATCH | `'/interests' + '/{interest_id}'` | `update_interest` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 542) |
| POST | `'/interests' + '/{interest_id}/feedback'` | `submit_feedback` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 661) |
| POST | `'/interests' + '/{interest_id}/reactivate'` | `reactivate_interest` | [apps/api/src/domains/interests/router.py](../../../apps/api/src/domains/interests/router.py) (line 768) |

### journals

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/journals' + '/themes'` | `list_themes` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 166) |
| GET | `'/journals' + '/settings'` | `get_journal_settings` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 184) |
| PATCH | `'/journals' + '/settings'` | `update_journal_settings` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 194) |
| GET | `'/journals' + '/export'` | `export_entries` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 233) |
| GET | `'/journals' + ''` | `list_entries` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 348) |
| POST | `'/journals' + ''` | `create_entry` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 386) |
| PATCH | `'/journals' + '/{entry_id}'` | `update_entry` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 409) |
| DELETE | `'/journals' + '/{entry_id}'` | `delete_entry` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 441) |
| DELETE | `'/journals' + ''` | `delete_all_entries` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 462) |
| POST | `'/journals' + '/consolidate'` | `consolidate_now` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 473) |
| GET | `'/journals' + '/portrait'` | `get_portrait` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 560) |
| POST | `'/journals' + '/portrait/feedback'` | `portrait_feedback` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 581) |
| GET | `'/journals' + '/{entry_id}/provenance'` | `get_entry_provenance` | [apps/api/src/domains/journals/router.py](../../../apps/api/src/domains/journals/router.py) (line 695) |

### live

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/live' + '/config'` | `live_config` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 80) |
| POST | `'/live' + '/models/discover'` | `discover_models` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 116) |
| GET | `'/live' + '/voices/published'` | `published_voices` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 132) |
| POST | `'/live' + '/voices/sample'` | `sample_voice` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 145) |
| POST | `'/live' + '/connector/activate'` | `activate_connector` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 160) |
| GET | `'/live' + '/connectors'` | `get_connectors` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 176) |
| PUT | `'/live' + '/connectors/{provider}'` | `put_connector` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 191) |
| GET | `'/live' + '/models'` | `list_models` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 206) |
| GET | `'/live' + '/voices'` | `list_voices` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 214) |
| GET | `'/live' + '/preferences'` | `get_preferences` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 233) |
| PUT | `'/live' + '/preferences'` | `put_preferences` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 241) |
| POST | `'/live' + '/sessions'` | `start_session` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 258) |
| POST | `'/live' + '/sessions/{session_id}/tools'` | `run_session_tool` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 282) |
| POST | `'/live' + '/sessions/{session_id}/credential'` | `renew_credential` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 308) |
| POST | `'/live' + '/sessions/{session_id}/offer'` | `exchange_offer` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 322) |
| POST | `'/live' + '/sessions/{session_id}/extend'` | `extend_session` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 337) |
| POST | `'/live' + '/sessions/{session_id}/standby'` | `standby_session` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 351) |
| POST | `'/live' + '/sessions/{session_id}/wake'` | `wake_session` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 370) |
| POST | `'/live' + '/sessions/{session_id}/turns'` | `archive_turn` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 392) |
| POST | `'/live' + '/sessions/{session_id}/end'` | `end_session` | [apps/api/src/domains/live/router.py](../../../apps/api/src/domains/live/router.py) (line 407) |

### llm

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/admin/llm/pricing/sheet' + '/export.xlsx'` | `export_pricing_sheet` | [apps/api/src/domains/llm/pricing_sheet_router.py](../../../apps/api/src/domains/llm/pricing_sheet_router.py) (line 71) |
| POST | `'/admin/llm/pricing/sheet' + '/import'` | `import_pricing_sheet` | [apps/api/src/domains/llm/pricing_sheet_router.py](../../../apps/api/src/domains/llm/pricing_sheet_router.py) (line 114) |
| GET | `'/admin/llm' + '/pricing'` | `list_active_pricing` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 122) |
| GET | `'/admin/llm' + '/catalogue-status'` | `get_catalogue_status` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 246) |
| GET | `'/admin/llm' + '/reasoning-family'` | `get_reasoning_family` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 327) |
| POST | `'/admin/llm' + '/pricing'` | `create_pricing` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 348) |
| PUT | `'/admin/llm' + '/pricing/{model_name}'` | `update_pricing` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 422) |
| DELETE | `'/admin/llm' + '/pricing/{pricing_id}'` | `deactivate_pricing` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 505) |
| POST | `'/admin/llm' + '/pricing/reload-cache'` | `reload_pricing_cache` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 565) |
| GET | `'/admin/llm' + '/currencies'` | `list_active_currency_rates` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 622) |
| POST | `'/admin/llm' + '/currencies'` | `create_currency_rate` | [apps/api/src/domains/llm/router.py](../../../apps/api/src/domains/llm/router.py) (line 655) |

### llm_config

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/debug/jev' + ''` | `get_jev_calls` | [apps/api/src/domains/llm_config/jev_debug_router.py](../../../apps/api/src/domains/llm_config/jev_debug_router.py) (line 18) |
| GET | `'/admin/llm-config' + '/jev'` | `get_jev` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 44) |
| PATCH | `'/admin/llm-config' + '/jev'` | `patch_jev` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 53) |
| GET | `'/admin/llm-config' + '/providers'` | `get_providers` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 68) |
| PUT | `'/admin/llm-config' + '/providers/{provider}'` | `update_provider_key` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 82) |
| DELETE | `'/admin/llm-config' + '/providers/{provider}'` | `delete_provider_key` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 102) |
| GET | `'/admin/llm-config' + '/types'` | `get_types` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 124) |
| GET | `'/admin/llm-config' + '/types/{llm_type}'` | `get_type` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 139) |
| PUT | `'/admin/llm-config' + '/types/{llm_type}'` | `update_type` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 157) |
| POST | `'/admin/llm-config' + '/types/{llm_type}/reset'` | `reset_type` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 177) |
| GET | `'/admin/llm-config' + '/metadata/models'` | `get_models_metadata` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 199) |
| GET | `'/admin/llm-config' + '/providers/ollama/models'` | `get_ollama_models` | [apps/api/src/domains/llm_config/router.py](../../../apps/api/src/domains/llm_config/router.py) (line 236) |

### meetings

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/meetings' + ''` | `start_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 74) |
| GET | `'/meetings' + '/active'` | `get_active_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 88) |
| GET | `'/meetings' + ''` | `list_meetings` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 103) |
| POST | `'/meetings' + '/bulk-delete'` | `bulk_delete_meetings` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 127) |
| GET | `'/meetings' + '/templates'` | `list_templates` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 139) |
| POST | `'/meetings' + '/templates'` | `create_template` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 153) |
| POST | `'/meetings' + '/templates/bulk-duplicate'` | `bulk_duplicate_templates` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 166) |
| POST | `'/meetings' + '/templates/bulk-delete'` | `bulk_delete_templates` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 182) |
| GET | `'/meetings' + '/templates/{ref}'` | `get_template` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 192) |
| PUT | `'/meetings' + '/templates/{ref}'` | `update_template` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 203) |
| DELETE | `'/meetings' + '/templates/{ref}'` | `delete_template` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 216) |
| GET | `'/meetings' + '/preferences'` | `get_preferences` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 225) |
| PUT | `'/meetings' + '/preferences'` | `put_preferences` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 235) |
| GET | `'/meetings' + '/{meeting_id}'` | `get_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 249) |
| PUT | `'/meetings' + '/{meeting_id}/segments/{sequence}'` | `put_segment` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 265) |
| POST | `'/meetings' + '/{meeting_id}/stop'` | `stop_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 289) |
| POST | `'/meetings' + '/{meeting_id}/resume'` | `resume_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 306) |
| POST | `'/meetings' + '/{meeting_id}/retry'` | `retry_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 321) |
| POST | `'/meetings' + '/{meeting_id}/regenerate'` | `regenerate_minutes` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 339) |
| POST | `'/meetings' + '/{meeting_id}/reformat'` | `reformat_minutes` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 357) |
| GET | `'/meetings' + '/{meeting_id}/pdf'` | `download_pdf` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 376) |
| POST | `'/meetings' + '/{meeting_id}/email'` | `email_minutes` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 396) |
| PATCH | `'/meetings' + '/{meeting_id}'` | `patch_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 407) |
| POST | `'/meetings' + '/{meeting_id}/report/reset'` | `reset_report` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 426) |
| DELETE | `'/meetings' + '/{meeting_id}/transcript'` | `delete_transcript` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 444) |
| DELETE | `'/meetings' + '/{meeting_id}'` | `delete_meeting` | [apps/api/src/domains/meetings/router.py](../../../apps/api/src/domains/meetings/router.py) (line 455) |

### memories

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/memories' + '/categories'` | `list_categories` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 121) |
| GET | `'/memories' + '/export'` | `export_memories` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 133) |
| GET | `'/memories' + ''` | `list_memories` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 204) |
| GET | `'/memories' + '/{memory_id}'` | `get_memory` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 269) |
| POST | `'/memories' + ''` | `create_memory` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 309) |
| PATCH | `'/memories' + '/{memory_id}'` | `update_memory` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 355) |
| PATCH | `'/memories' + '/{memory_id}/pin'` | `toggle_pin_memory` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 414) |
| DELETE | `'/memories' + '/{memory_id}'` | `delete_memory` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 465) |
| DELETE | `'/memories' + ''` | `delete_all_memories` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 511) |
| GET | `'/memories' + '/{memory_id}/provenance'` | `get_memory_provenance` | [apps/api/src/domains/memories/router.py](../../../apps/api/src/domains/memories/router.py) (line 569) |

### notifications

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/notifications' + '/push-config'` | `get_push_config` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 76) |
| POST | `'/notifications' + '/register-token'` | `register_fcm_token` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 118) |
| POST | `'/notifications' + '/unregister-token'` | `unregister_fcm_token` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 156) |
| GET | `'/notifications' + '/tokens'` | `list_user_tokens` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 192) |
| DELETE | `'/notifications' + '/tokens/{token_id}'` | `delete_token_by_id` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 229) |
| GET | `'/notifications' + '/stream'` | `stream_notifications` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 274) |
| POST | `'/notifications' + '/admin/broadcast'` | `send_broadcast` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 433) |
| GET | `'/notifications' + '/admin/broadcasts'` | `list_broadcast_history` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 501) |
| GET | `'/notifications' + '/broadcasts/unread'` | `get_unread_broadcasts` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 532) |
| POST | `'/notifications' + '/broadcasts/{broadcast_id}/read'` | `mark_broadcast_read` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 568) |
| POST | `'/notifications' + '/test'` | `send_test_notification` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 601) |
| GET | `'/notifications' + '/hub-counts'` | `get_hub_counts` | [apps/api/src/domains/notifications/router.py](../../../apps/api/src/domains/notifications/router.py) (line 648) |

### open_loops

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/open-loops' + ''` | `list_open_loops` | [apps/api/src/domains/open_loops/router.py](../../../apps/api/src/domains/open_loops/router.py) (line 47) |
| POST | `'/open-loops' + '/{loop_id}/close'` | `close_open_loop` | [apps/api/src/domains/open_loops/router.py](../../../apps/api/src/domains/open_loops/router.py) (line 67) |
| PATCH | `'/open-loops' + '/{loop_id}'` | `update_open_loop` | [apps/api/src/domains/open_loops/router.py](../../../apps/api/src/domains/open_loops/router.py) (line 101) |

### peers

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/peers' + '/me'` | `get_discovery_state` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 93) |
| PUT | `'/peers' + '/me'` | `update_discovery_state` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 115) |
| POST | `'/peers' + '/discovery/search'` | `search_discovery` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 148) |
| POST | `'/peers' + '/requests'` | `create_request` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 165) |
| GET | `'/peers' + '/requests'` | `list_requests` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 184) |
| POST | `'/peers' + '/requests/{connection_id}/respond'` | `respond_to_request` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 199) |
| GET | `'/peers' + '/connections'` | `list_connections` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 219) |
| DELETE | `'/peers' + '/connections/{connection_id}'` | `remove_connection` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 234) |
| PUT | `'/peers' + '/connections/{connection_id}/shares'` | `set_or_delete_share` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 256) |
| POST | `'/peers' + '/connections/{connection_id}/images'` | `share_image_with_connection` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 280) |
| GET | `'/peers' + '/access-log'` | `list_access_log` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 308) |
| POST | `'/peers' + '/blocks'` | `create_block` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 324) |
| DELETE | `'/peers' + '/blocks/{peer_id}'` | `delete_block` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 342) |
| GET | `'/peers' + '/blocks'` | `list_blocks` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 360) |
| GET | `'/peers' + '/messages'` | `list_relayed_messages` | [apps/api/src/domains/peers/router.py](../../../apps/api/src/domains/peers/router.py) (line 384) |

### personalities

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/personalities' + ''` | `list_personalities` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 43) |
| GET | `'/personalities' + '/current'` | `get_current_personality` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 57) |
| PATCH | `'/personalities' + '/current'` | `update_current_personality` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 78) |
| GET | `'/personalities' + '/admin'` | `list_all_personalities` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 122) |
| GET | `'/personalities' + '/admin/{personality_id}'` | `get_personality` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 136) |
| POST | `'/personalities' + '/admin'` | `create_personality` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 150) |
| PATCH | `'/personalities' + '/admin/{personality_id}'` | `update_personality` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 175) |
| DELETE | `'/personalities' + '/admin/{personality_id}'` | `delete_personality` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 216) |
| POST | `'/personalities' + '/admin/{personality_id}/translations'` | `add_translation` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 240) |
| POST | `'/personalities' + '/admin/{personality_id}/auto-translate'` | `trigger_auto_translation` | [apps/api/src/domains/personalities/router.py](../../../apps/api/src/domains/personalities/router.py) (line 263) |

### plugins

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/plugins' + '/import'` | `import_plugin` | [apps/api/src/domains/plugins/router.py](../../../apps/api/src/domains/plugins/router.py) (line 51) |
| POST | `'/plugins' + '/import-from-url'` | `import_plugin_from_url` | [apps/api/src/domains/plugins/router.py](../../../apps/api/src/domains/plugins/router.py) (line 81) |
| GET | `'/plugins' + ''` | `list_plugins` | [apps/api/src/domains/plugins/router.py](../../../apps/api/src/domains/plugins/router.py) (line 117) |
| DELETE | `'/plugins' + '/{plugin_id}'` | `delete_plugin` | [apps/api/src/domains/plugins/router.py](../../../apps/api/src/domains/plugins/router.py) (line 160) |

### product

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/product' + '/public-demo-link'` | `get_public_demo_link` | [apps/api/src/domains/product/public_demo_link.py](../../../apps/api/src/domains/product/public_demo_link.py) (line 118) |
| GET | `'/admin/public-demo-link' + ''` | `get_admin_public_demo_link` | [apps/api/src/domains/product/public_demo_link_admin.py](../../../apps/api/src/domains/product/public_demo_link_admin.py) (line 120) |
| PUT | `'/admin/public-demo-link' + ''` | `update_admin_public_demo_link` | [apps/api/src/domains/product/public_demo_link_admin.py](../../../apps/api/src/domains/product/public_demo_link_admin.py) (line 136) |
| POST | `'/product' + '/events'` | `ingest_client_events` | [apps/api/src/domains/product/router.py](../../../apps/api/src/domains/product/router.py) (line 118) |
| GET | `'/product' + '/me/results'` | `get_personal_results` | [apps/api/src/domains/product/router.py](../../../apps/api/src/domains/product/router.py) (line 222) |
| POST | `'/product' + '/showroom-events'` | `ingest_showroom_events` | [apps/api/src/domains/product/showroom_telemetry.py](../../../apps/api/src/domains/product/showroom_telemetry.py) (line 97) |

### psyche

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/psyche' + '/state'` | `get_psyche_state` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 53) |
| GET | `'/psyche' + '/summary'` | `get_psyche_summary` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 90) |
| GET | `'/psyche' + '/expression'` | `get_expression_profile` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 116) |
| GET | `'/psyche' + '/settings'` | `get_psyche_settings` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 159) |
| PATCH | `'/psyche' + '/settings'` | `update_psyche_settings` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 172) |
| POST | `'/psyche' + '/reset'` | `reset_psyche_state` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 205) |
| GET | `'/psyche' + '/history'` | `get_psyche_history` | [apps/api/src/domains/psyche/router.py](../../../apps/api/src/domains/psyche/router.py) (line 235) |

### push_channels

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/webhooks' + '/google'` | `google_channel_webhook` | [apps/api/src/domains/push_channels/router.py](../../../apps/api/src/domains/push_channels/router.py) (line 31) |
| POST | `'/webhooks' + '/google/pubsub'` | `google_pubsub_webhook` | [apps/api/src/domains/push_channels/router.py](../../../apps/api/src/domains/push_channels/router.py) (line 48) |

### push_relay

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/push-relay' + '/devices'` | `register_device` | [apps/api/src/domains/push_relay/router.py](../../../apps/api/src/domains/push_relay/router.py) (line 54) |
| POST | `'/push-relay' + '/wake'` | `wake_device` | [apps/api/src/domains/push_relay/router.py](../../../apps/api/src/domains/push_relay/router.py) (line 89) |

### radio

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/radio' + '/sessions'` | `start_session` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 102) |
| POST | `'/radio' + '/sessions/{session_id}/playhead'` | `report_playhead` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 122) |
| POST | `'/radio' + '/sessions/{session_id}/stop'` | `stop_session` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 139) |
| GET | `'/radio' + '/sessions/{session_id}/segments/{seq}/audio'` | `segment_audio` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 153) |
| GET | `'/radio' + '/options'` | `get_options` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 171) |
| GET | `'/radio' + '/budget'` | `get_budget` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 188) |
| GET | `'/radio' + '/articles/{article_id}'` | `get_article` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 213) |
| GET | `'/radio' + '/preferences'` | `get_preferences` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 225) |
| PUT | `'/radio' + '/preferences'` | `put_preferences` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 241) |
| GET | `'/radio' + '/sources'` | `get_sources` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 259) |
| PATCH | `'/radio' + '/sources/{source_id}'` | `patch_source` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 272) |
| DELETE | `'/radio' + '/heard'` | `delete_heard` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 290) |
| POST | `'/radio' + '/sources/preview'` | `preview_source` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 303) |
| POST | `'/radio' + '/sources'` | `post_source` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 324) |
| DELETE | `'/radio' + '/sources/{source_id}'` | `delete_source` | [apps/api/src/domains/radio/router.py](../../../apps/api/src/domains/radio/router.py) (line 345) |

### rag_spaces

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'' + '/documents'` | `list_attachable_documents` | [apps/api/src/domains/rag_spaces/documents_router.py](../../../apps/api/src/domains/rag_spaces/documents_router.py) (line 61) |
| GET | `'' + '/{space_id}/mail-labels'` | `list_mail_labels` | [apps/api/src/domains/rag_spaces/mail_router.py](../../../apps/api/src/domains/rag_spaces/mail_router.py) (line 43) |
| POST | `'' + '/{space_id}/mail-sources'` | `link_mail_label` | [apps/api/src/domains/rag_spaces/mail_router.py](../../../apps/api/src/domains/rag_spaces/mail_router.py) (line 59) |
| GET | `'' + '/{space_id}/mail-sources'` | `list_mail_sources` | [apps/api/src/domains/rag_spaces/mail_router.py](../../../apps/api/src/domains/rag_spaces/mail_router.py) (line 77) |
| DELETE | `'' + '/{space_id}/mail-sources/{source_id}'` | `unlink_mail_label` | [apps/api/src/domains/rag_spaces/mail_router.py](../../../apps/api/src/domains/rag_spaces/mail_router.py) (line 92) |
| POST | `'' + '/{space_id}/mail-sources/{source_id}/sync'` | `sync_mail_label` | [apps/api/src/domains/rag_spaces/mail_router.py](../../../apps/api/src/domains/rag_spaces/mail_router.py) (line 109) |
| GET | `'' + '/{space_id}/mail-sources/{source_id}/sync-status'` | `get_mail_sync_status` | [apps/api/src/domains/rag_spaces/mail_router.py](../../../apps/api/src/domains/rag_spaces/mail_router.py) (line 137) |
| POST | `'/rag-spaces' + '/admin/reindex'` | `trigger_reindex` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 94) |
| GET | `'/rag-spaces' + '/admin/reindex/status'` | `get_reindex_status` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 113) |
| GET | `'/rag-spaces' + '/admin/system-spaces'` | `list_system_spaces` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 131) |
| POST | `'/rag-spaces' + '/admin/system-spaces/{space_name}/reindex'` | `reindex_system_space` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 149) |
| GET | `'/rag-spaces' + '/admin/system-spaces/{space_name}/staleness'` | `check_system_space_staleness` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 204) |
| GET | `'/rag-spaces' + ''` | `list_spaces` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 230) |
| POST | `'/rag-spaces' + ''` | `create_space` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 249) |
| GET | `'/rag-spaces' + '/{space_id}'` | `get_space_detail` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 275) |
| PATCH | `'/rag-spaces' + '/{space_id}'` | `update_space` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 297) |
| DELETE | `'/rag-spaces' + '/{space_id}'` | `delete_space` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 319) |
| PATCH | `'/rag-spaces' + '/{space_id}/toggle'` | `toggle_space` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 334) |
| POST | `'/rag-spaces' + '/{space_id}/documents'` | `upload_document` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 356) |
| GET | `'/rag-spaces' + '/{space_id}/documents/archive'` | `download_documents_archive` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 440) |
| POST | `'/rag-spaces' + '/{space_id}/documents/move'` | `move_space_documents` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 461) |
| POST | `'/rag-spaces' + '/{space_id}/documents/bulk-delete'` | `bulk_delete_space_documents` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 476) |
| GET | `'/rag-spaces' + '/{space_id}/documents/{document_id}/download'` | `download_space_document` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 490) |
| DELETE | `'/rag-spaces' + '/{space_id}/documents/{document_id}'` | `delete_document` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 510) |
| GET | `'/rag-spaces' + '/{space_id}/documents/{document_id}/status'` | `get_document_status` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 526) |
| GET | `'/rag-spaces' + '/{space_id}/drive-browse'` | `browse_drive_contents` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 554) |
| POST | `'/rag-spaces' + '/{space_id}/drive-sources'` | `link_drive_folder` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 572) |
| GET | `'/rag-spaces' + '/{space_id}/drive-sources'` | `list_drive_sources` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 589) |
| DELETE | `'/rag-spaces' + '/{space_id}/drive-sources/{source_id}'` | `unlink_drive_folder` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 605) |
| GET | `'/rag-spaces' + '/{space_id}/drive-sources/{source_id}/preflight'` | `preflight_drive_sync` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 622) |
| POST | `'/rag-spaces' + '/{space_id}/drive-sources/{source_id}/sync'` | `sync_drive_folder` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 640) |
| GET | `'/rag-spaces' + '/{space_id}/drive-sources/{source_id}/sync-status'` | `get_drive_sync_status` | [apps/api/src/domains/rag_spaces/router.py](../../../apps/api/src/domains/rag_spaces/router.py) (line 684) |

### relations

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| PUT | `'/relations' + '/favorites/{name}'` | `add_relation_favorite` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 75) |
| DELETE | `'/relations' + '/favorites/{name}'` | `remove_relation_favorite` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 89) |
| POST | `'/relations' + '/merges'` | `merge_relations` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 106) |
| DELETE | `'/relations' + '/merges/{name}'` | `split_relation` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 131) |
| PATCH | `'/relations' + '/settings'` | `update_relation_settings` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 153) |
| GET | `'/relations' + '/overview-scope'` | `get_overview_scope` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 171) |
| PUT | `'/relations' + '/overview-scope'` | `set_overview_scope` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 189) |
| GET | `'/relations' + ''` | `get_relations_overview` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 203) |
| GET | `'/relations' + '/{name}/debrief'` | `get_relation_debrief` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 228) |
| POST | `'/relations' + '/{name}/debrief'` | `build_relation_debrief` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 249) |
| GET | `'/relations' + '/{name}/context'` | `get_relation_context` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 278) |
| GET | `'/relations' + '/{name}'` | `get_relation_detail` | [apps/api/src/domains/relations/router.py](../../../apps/api/src/domains/relations/router.py) (line 300) |

### reminders

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/reminders' + ''` | `list_pending_reminders` | [apps/api/src/domains/reminders/router.py](../../../apps/api/src/domains/reminders/router.py) (line 149) |
| GET | `'/reminders' + '/detail'` | `list_reminder_details` | [apps/api/src/domains/reminders/router.py](../../../apps/api/src/domains/reminders/router.py) (line 185) |
| POST | `'/reminders' + ''` | `create_reminder` | [apps/api/src/domains/reminders/router.py](../../../apps/api/src/domains/reminders/router.py) (line 223) |
| PATCH | `'/reminders' + '/{reminder_id}'` | `update_reminder` | [apps/api/src/domains/reminders/router.py](../../../apps/api/src/domains/reminders/router.py) (line 263) |
| DELETE | `'/reminders' + '/{reminder_id}'` | `cancel_reminder` | [apps/api/src/domains/reminders/router.py](../../../apps/api/src/domains/reminders/router.py) (line 308) |

### scheduled_actions

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/scheduled-actions' + ''` | `list_scheduled_actions` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 58) |
| GET | `'/scheduled-actions' + '/week'` | `week_scheduled_actions` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 94) |
| POST | `'/scheduled-actions' + ''` | `create_scheduled_action` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 140) |
| PATCH | `'/scheduled-actions' + '/{action_id}'` | `update_scheduled_action` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 175) |
| DELETE | `'/scheduled-actions' + '/{action_id}'` | `delete_scheduled_action` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 207) |
| PATCH | `'/scheduled-actions' + '/{action_id}/toggle'` | `toggle_scheduled_action` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 235) |
| POST | `'/scheduled-actions' + '/{action_id}/execute'` | `execute_scheduled_action` | [apps/api/src/domains/scheduled_actions/router.py](../../../apps/api/src/domains/scheduled_actions/router.py) (line 267) |

### skill_library

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/skill-library' + '/search'` | `search` | [apps/api/src/domains/skill_library/router.py](../../../apps/api/src/domains/skill_library/router.py) (line 83) |
| GET | `'/skill-library' + '/preview'` | `preview` | [apps/api/src/domains/skill_library/router.py](../../../apps/api/src/domains/skill_library/router.py) (line 106) |
| POST | `'/skill-library' + '/install'` | `install` | [apps/api/src/domains/skill_library/router.py](../../../apps/api/src/domains/skill_library/router.py) (line 145) |
| GET | `'/skill-library' + '/installed'` | `installed` | [apps/api/src/domains/skill_library/router.py](../../../apps/api/src/domains/skill_library/router.py) (line 159) |
| GET | `'/skill-library' + '/installed/{skill_id}/update'` | `update_preview` | [apps/api/src/domains/skill_library/router.py](../../../apps/api/src/domains/skill_library/router.py) (line 173) |
| POST | `'/skill-library' + '/installed/{skill_id}/update'` | `update` | [apps/api/src/domains/skill_library/router.py](../../../apps/api/src/domains/skill_library/router.py) (line 191) |

### skills

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/skill-proposals' + '/{proposal_id}'` | `read_proposal` | [apps/api/src/domains/skills/proposal_router.py](../../../apps/api/src/domains/skills/proposal_router.py) (line 58) |
| POST | `'/skill-proposals' + '/{proposal_id}/install'` | `install_proposal` | [apps/api/src/domains/skills/proposal_router.py](../../../apps/api/src/domains/skills/proposal_router.py) (line 86) |
| GET | `'/skills' + ''` | `list_skills` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 225) |
| GET | `'/skills' + '/admin/list'` | `list_admin_skills` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 248) |
| GET | `'/skills' + '/admin/{skill_name}/download'` | `download_admin_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 269) |
| DELETE | `'/skills' + '/admin/{skill_name}'` | `delete_admin_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 294) |
| PATCH | `'/skills' + '/admin/{skill_name}/description'` | `update_admin_skill_description` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 331) |
| GET | `'/skills' + '/{skill_name}/download'` | `download_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 398) |
| GET | `'/skills' + '/{skill_name}/preview'` | `skill_preview` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 431) |
| POST | `'/skills' + '/import'` | `import_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 475) |
| POST | `'/skills' + '/import-from-url'` | `import_skill_from_url` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 505) |
| POST | `'/skills' + '/admin/import'` | `import_admin_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 567) |
| DELETE | `'/skills' + '/{skill_name}'` | `delete_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 593) |
| PATCH | `'/skills' + '/{skill_name}/toggle'` | `toggle_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 643) |
| PATCH | `'/skills' + '/admin/{skill_name}/system-toggle'` | `admin_system_toggle_skill` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 669) |
| POST | `'/skills' + '/admin/{skill_name}/translate-description'` | `translate_skill_description` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 708) |
| POST | `'/skills' + '/reload'` | `reload_skills` | [apps/api/src/domains/skills/router.py](../../../apps/api/src/domains/skills/router.py) (line 765) |

### system_settings

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/system-settings' + '/debug-panel-status'` | `get_debug_panel_status` | [apps/api/src/domains/system_settings/public_router.py](../../../apps/api/src/domains/system_settings/public_router.py) (line 36) |
| GET | `'/admin/system-settings' + '/debug-panel'` | `get_debug_panel_enabled` | [apps/api/src/domains/system_settings/router.py](../../../apps/api/src/domains/system_settings/router.py) (line 50) |
| PUT | `'/admin/system-settings' + '/debug-panel'` | `update_debug_panel_enabled` | [apps/api/src/domains/system_settings/router.py](../../../apps/api/src/domains/system_settings/router.py) (line 70) |
| GET | `'/admin/system-settings' + '/debug-panel-user-access'` | `get_debug_panel_user_access` | [apps/api/src/domains/system_settings/router.py](../../../apps/api/src/domains/system_settings/router.py) (line 110) |
| PUT | `'/admin/system-settings' + '/debug-panel-user-access'` | `update_debug_panel_user_access` | [apps/api/src/domains/system_settings/router.py](../../../apps/api/src/domains/system_settings/router.py) (line 130) |

### telephony

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| POST | `'/telephony' + '/connector/validate-key'` | `validate_key` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 76) |
| POST | `'/telephony' + '/connector/activate'` | `activate` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 95) |
| DELETE | `'/telephony' + '/connector'` | `deactivate` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 126) |
| POST | `'/telephony' + '/webhook'` | `telephony_webhook` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 140) |
| GET | `'/telephony' + '/calls'` | `list_calls` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 188) |
| GET | `'/telephony' + '/identity'` | `get_identity` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 282) |
| POST | `'/telephony' + '/identity/verify'` | `start_identity_verification` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 297) |
| POST | `'/telephony' + '/identity/confirm'` | `confirm_identity_verification` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 317) |
| PUT | `'/telephony' + '/identity/number'` | `set_identity_number` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 334) |
| DELETE | `'/telephony' + '/identity/number'` | `clear_identity_number` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 351) |
| PATCH | `'/telephony' + '/identity'` | `update_identity` | [apps/api/src/domains/telephony/router.py](../../../apps/api/src/domains/telephony/router.py) (line 364) |

### usage_limits

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/usage-limits' + '/me'` | `get_my_usage_limits` | [apps/api/src/domains/usage_limits/router.py](../../../apps/api/src/domains/usage_limits/router.py) (line 74) |
| GET | `'/usage-limits' + '/admin/users'` | `list_users_usage_limits` | [apps/api/src/domains/usage_limits/router.py](../../../apps/api/src/domains/usage_limits/router.py) (line 101) |
| PUT | `'/usage-limits' + '/admin/users/{user_id}/limits'` | `update_user_limits` | [apps/api/src/domains/usage_limits/router.py](../../../apps/api/src/domains/usage_limits/router.py) (line 143) |
| PUT | `'/usage-limits' + '/admin/users/{user_id}/block'` | `toggle_user_block` | [apps/api/src/domains/usage_limits/router.py](../../../apps/api/src/domains/usage_limits/router.py) (line 180) |
| GET | `'/usage-limits' + '/admin/instance-daily-budget'` | `get_instance_daily_budget` | [apps/api/src/domains/usage_limits/router.py](../../../apps/api/src/domains/usage_limits/router.py) (line 225) |
| PUT | `'/usage-limits' + '/admin/instance-daily-budget'` | `update_instance_daily_budget` | [apps/api/src/domains/usage_limits/router.py](../../../apps/api/src/domains/usage_limits/router.py) (line 248) |
| POST | `'/usage-limits' + '/admin/ws/ticket'` | `create_admin_ws_ticket` | [apps/api/src/domains/usage_limits/websocket.py](../../../apps/api/src/domains/usage_limits/websocket.py) (line 57) |
| WEBSOCKET | `'/usage-limits' + '/admin/ws'` | `admin_usage_ws` | [apps/api/src/domains/usage_limits/websocket.py](../../../apps/api/src/domains/usage_limits/websocket.py) (line 91) |

### user_mcp

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/mcp/admin-servers' + ''` | `list_admin_servers` | [apps/api/src/domains/user_mcp/admin_router.py](../../../apps/api/src/domains/user_mcp/admin_router.py) (line 52) |
| PATCH | `'/mcp/admin-servers' + '/{server_key}/toggle'` | `toggle_admin_server` | [apps/api/src/domains/user_mcp/admin_router.py](../../../apps/api/src/domains/user_mcp/admin_router.py) (line 101) |
| POST | `'/mcp/admin-servers' + '/{server_key}/app/call-tool'` | `admin_app_proxy_call_tool` | [apps/api/src/domains/user_mcp/admin_router.py](../../../apps/api/src/domains/user_mcp/admin_router.py) (line 156) |
| POST | `'/mcp/admin-servers' + '/{server_key}/app/read-resource'` | `admin_app_proxy_read_resource` | [apps/api/src/domains/user_mcp/admin_router.py](../../../apps/api/src/domains/user_mcp/admin_router.py) (line 201) |
| GET | `'/mcp/servers' + ''` | `list_servers` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 155) |
| POST | `'/mcp/servers' + ''` | `create_server` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 187) |
| PATCH | `'/mcp/servers' + '/{server_id}'` | `update_server` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 215) |
| DELETE | `'/mcp/servers' + '/{server_id}'` | `delete_server` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 243) |
| PATCH | `'/mcp/servers' + '/{server_id}/toggle'` | `toggle_server` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 274) |
| POST | `'/mcp/servers' + '/{server_id}/test'` | `test_connection` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 301) |
| POST | `'/mcp/servers' + '/{server_id}/generate-description'` | `generate_description` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 345) |
| POST | `'/mcp/servers' + '/{server_id}/oauth/disconnect'` | `oauth_disconnect` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 379) |
| POST | `'/mcp/servers' + '/{server_id}/oauth/authorize'` | `oauth_authorize` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 409) |
| POST | `'/mcp/servers' + '/{server_id}/app/call-tool'` | `app_proxy_call_tool` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 481) |
| POST | `'/mcp/servers' + '/{server_id}/app/read-resource'` | `app_proxy_read_resource` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 521) |
| GET | `'/mcp/servers' + '/oauth/callback'` | `oauth_callback` | [apps/api/src/domains/user_mcp/router.py](../../../apps/api/src/domains/user_mcp/router.py) (line 566) |

### users

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/users' + '/timezones'` | `list_common_timezones` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 58) |
| GET | `'/users' + ''` | `get_users` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 74) |
| GET | `'/users' + '/{user_id}'` | `get_user` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 96) |
| PATCH | `'/users' + '/{user_id}'` | `update_user` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 114) |
| DELETE | `'/users' + '/{user_id}'` | `delete_user` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 133) |
| GET | `'/users' + '/search/by-email'` | `search_users_by_email` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 152) |
| GET | `'/users' + '/me/home-location'` | `get_home_location` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 173) |
| PUT | `'/users' + '/me/home-location'` | `set_home_location` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 192) |
| DELETE | `'/users' + '/me/home-location'` | `clear_home_location` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 208) |
| GET | `'/users' + '/me/settings-shortcuts'` | `get_settings_shortcuts` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 234) |
| PUT | `'/users' + '/me/settings-shortcuts'` | `put_settings_shortcuts` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 250) |
| GET | `'/users' + '/admin/search'` | `search_users_admin` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 283) |
| PATCH | `'/users' + '/admin/{user_id}/activation'` | `update_user_activation_admin` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 342) |
| DELETE | `'/users' + '/admin/{user_id}/delete-account'` | `delete_user_account_admin` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 381) |
| DELETE | `'/users' + '/admin/{user_id}/gdpr'` | `delete_user_gdpr_admin` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 431) |
| GET | `'/users' + '/admin/autocomplete'` | `autocomplete_users_admin` | [apps/api/src/domains/users/router.py](../../../apps/api/src/domains/users/router.py) (line 463) |

### voice

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/admin/voice' + '/voices'` | `list_voices` | [apps/api/src/domains/voice/admin_router.py](../../../apps/api/src/domains/voice/admin_router.py) (line 85) |
| POST | `'/voice' + '/ticket'` | `create_websocket_ticket` | [apps/api/src/domains/voice/router.py](../../../apps/api/src/domains/voice/router.py) (line 123) |
| WEBSOCKET | `'/voice' + '/ws/audio'` | `websocket_audio` | [apps/api/src/domains/voice/router.py](../../../apps/api/src/domains/voice/router.py) (line 169) |

### workboard

| Method | Prefix + path (source expressions) | Handler | Source |
|---|---|---|---|
| GET | `'/workboard' + '/tickets'` | `list_board` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 69) |
| GET | `'/workboard' + '/needs-me'` | `needs_me` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 139) |
| GET | `'/workboard' + '/summary'` | `board_summary` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 170) |
| GET | `'/workboard' + '/tickets/{ticket_id}'` | `get_ticket` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 191) |
| POST | `'/workboard' + '/tickets'` | `create_ticket` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 221) |
| PATCH | `'/workboard' + '/tickets/{ticket_id}'` | `update_ticket` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 246) |
| POST | `'/workboard' + '/tickets/{ticket_id}/move'` | `move_ticket` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 273) |
| POST | `'/workboard' + '/tickets/{ticket_id}/run-now'` | `run_ticket_now` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 300) |
| POST | `'/workboard' + '/tickets/{ticket_id}/comments'` | `add_comment` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 326) |
| DELETE | `'/workboard' + '/tickets/{ticket_id}'` | `delete_ticket` | [apps/api/src/domains/workboard/router.py](../../../apps/api/src/domains/workboard/router.py) (line 353) |
