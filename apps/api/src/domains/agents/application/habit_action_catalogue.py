"""Habit management is independent of future learning and always requires human approval."""

from src.domains.agents.application.habit_action_schemas import (
    HabitDeleteRequest,
    HabitStatusRequest,
)
from src.domains.agents.application.habit_forget_schemas import HabitForgetRequest
from src.domains.agents.application.habit_recompute_schemas import HabitRecomputeRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

HABIT_STATUS_MANIFEST = ToolManifest(
    name="set_lia_habit_status_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to pause, resume or block one owned learned habit. Select habit_id using get_lia_habits_tool and explain using get_lia_habit_details_tool. Source statuses: active resumes use; paused retains the row and its learning evidence can still refresh; blocked retains a tombstone that prevents relearning. Resuming a blocked row explicitly removes that block. This does not change personal or operator learning switches, create automation, send an offer or cancel an offer already in flight. The full public source before/after is sealed; concurrent learning/status/evidence changes require new approval. Current actor, native availability and expiry are checked under the source account/row locks. An unchanged status is a confirmed no-op. No provider or recompute.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Owned habit and source target status",
            schema=HabitStatusRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_habits",
    initiative_eligible=False,
    semantic_keywords=["pause this habit", "resume my habit", "block habit relearning"],
    display=DisplayMetadata(emoji="📊", i18n_key="set_lia_habit_status", category="tool"),
)

HABIT_DELETE_MANIFEST = ToolManifest(
    name="delete_lia_habit_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to delete one owned learned habit. Select habit_id using get_lia_habits_tool. Removes only that saved row, including its block tombstone if blocked: the behaviour may be learned again. To prevent relearning retain the row with set_lia_habit_status_tool status blocked. Other habits, rhythm profile, durable activity and advisory recurrence evidence remain; personal/operator learning switches are unchanged. Full current public identity/evidence/status are compared under source account/row locks; changed or missing records need fresh approval. Active actor, native availability and expiry are checked before commit. No provider, recompute, message or automation.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exactly one owned habit identity",
            schema=HabitDeleteRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact removal confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_habits",
    initiative_eligible=False,
    semantic_keywords=["delete this learned habit", "remove this habit"],
    display=DisplayMetadata(emoji="📊", i18n_key="delete_lia_habit", category="tool"),
)

HABIT_FORGET_MANIFEST = ToolManifest(
    name="delete_all_lia_habits_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to forget all the current account's habit-learning state: every saved habit including blocked tombstones, rhythm profile and durable activity rollup, followed by cleanup of owned temporary recurrence and presence state. Confirmed scope is all_owned only. Counts cover every persisted record through bounded cursors; full private rows never enter the model or editor. Concurrent PostgreSQL evidence/profile/rollup changes require fresh approval. SQL erasure and Redis cleanup are separate: a failed cleanup is a committed partial failure with actual cleanup status, never full success or rollback. Conversations, outcomes and notification feedback are retained; learning preference/operator switches are unchanged, so later learning or explicit recompute may reconstruct habits from retained history. Redis traces generated concurrently after cleanup may reappear. Native access, ownership and expiry are checked under account/record locks. No provider or message.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Complete current owned habit-learning scope",
            schema=HabitForgetRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Exact bounded scope/count confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_habits",
    initiative_eligible=False,
    semantic_keywords=[
        "forget all my habits",
        "erase my learned rhythm",
        "reset habit learning evidence",
    ],
    display=DisplayMetadata(emoji="📊", i18n_key="delete_all_lia_habits", category="tool"),
)

HABIT_RECOMPUTE_MANIFEST = ToolManifest(
    name="recompute_lia_habits_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to run the current account's manual habit/rhythm recompute now, using the same force=True source unit as the settings UI. It evaluates current retained human history/activity and advisory recurrence evidence; windows and verdict are computed only after approval. It may promote/refresh/demote eligible habits; paused rows stay and blocked tombstones prevent relearning. Automatic-learning preference is unchanged; explicit manual recompute is available even when that preference is off, as in the UI, but operator HABITS capability must be enabled. Effective timezone/preference changes require fresh approval. Active owner, native availability, capability and expiry are checked under account locks before work and commit. Advisory seeding may prepare temporary traces independently of SQL; failure must not claim the profile was saved or all temporary work rolled back. Returns the actual source outcome/profile, including insufficient/no-activity results. No provider, message or automation.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Current owned source recompute",
            schema=HabitRecomputeRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact source action confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_habits",
    initiative_eligible=False,
    semantic_keywords=["recompute my activity rhythm", "refresh my learned habits now"],
    display=DisplayMetadata(emoji="📊", i18n_key="recompute_lia_habits", category="tool"),
)
