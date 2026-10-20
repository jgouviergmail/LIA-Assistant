"""Technical phone-ingestion limits; no LLM runs on this execution path."""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    SMS_CONTEXT_EXCERPT_CHARS_DEFAULT,
    SMS_CONTEXT_MAX_ITEMS_DEFAULT,
    SMS_CONTEXT_TOKEN_BUDGET_DEFAULT,
    SMS_SUMMARY_WINDOW_HOURS_DEFAULT,
)


class IngestionSettings(BaseSettings):
    sms_enabled: bool = Field(default=True)
    sms_summary_window_hours: int = Field(default=SMS_SUMMARY_WINDOW_HOURS_DEFAULT, ge=1, le=168)
    sms_context_max_items: int = Field(default=SMS_CONTEXT_MAX_ITEMS_DEFAULT, ge=1, le=3)
    sms_context_token_budget: int = Field(default=SMS_CONTEXT_TOKEN_BUDGET_DEFAULT, ge=256, le=1500)
    sms_context_excerpt_chars: int = Field(default=SMS_CONTEXT_EXCERPT_CHARS_DEFAULT, ge=32, le=256)
    ingestion_max_body_bytes: int = Field(default=262144, ge=1024, le=1048576)
    ingestion_max_batch_items: int = Field(default=50, ge=1, le=100)
    ingestion_source_requests_per_minute: int = Field(default=60, ge=1)
    ingestion_user_requests_per_minute: int = Field(default=120, ge=1)
    ingestion_max_receipts_per_user: int = Field(default=1000000, ge=1)
    sms_archive_max_logical_bytes: int = Field(default=1073741824, ge=1)
    ingestion_max_active_tokens_per_user: int = Field(default=20, ge=1, le=1000)
    sms_max_body_chars: int = Field(default=16000, ge=1, le=64000)
    sms_max_sender_chars: int = Field(default=256, ge=1, le=1024)
    sms_max_origin_chars: int = Field(default=32, ge=1, le=32)
    sms_max_future_skew_seconds: int = Field(default=300, ge=0, le=3600)
    sms_max_index_terms: int = Field(default=512, ge=16, le=2048)
    sms_search_max_query_terms: int = Field(default=32, ge=1, le=128)
    sms_search_max_candidates: int = Field(default=500, ge=1, le=2000)
    sms_search_timeout_ms: int = Field(default=2000, ge=100, le=10000)
    sms_identity_timeout_seconds: float = Field(default=5.0, ge=0.1, le=15.0)
    sms_directory_max_contacts: int = Field(default=2000, ge=1, le=10000)
    sms_search_max_verified_chars: int = Field(default=1048576, ge=1, le=8388608)
    sms_max_blocked_senders: int = Field(default=500, ge=1, le=5000)
    ingestion_delivery_interval_seconds: int = Field(default=15, ge=5, le=300)
    ingestion_delivery_lease_seconds: int = Field(default=60, ge=60, le=3600)
    ingestion_delivery_timeout_seconds: int = Field(default=30, ge=1, le=30)
    ingestion_delivery_sweep_seconds: int = Field(default=45, ge=1, le=300)
    ingestion_delivery_batch_size: int = Field(default=50, ge=1, le=500)
    ingestion_delivery_sql_timeout_seconds: float = Field(default=5.0, ge=0.1, le=10.0)
