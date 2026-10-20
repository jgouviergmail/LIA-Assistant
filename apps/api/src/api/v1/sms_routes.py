"""Compose SMS source routes and approved native workflows without a reverse domain edge."""

from fastapi import APIRouter

from src.domains.agents.application.sms_management_router import router as management_router
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.shared.relation_sms import register_relation_sms_reader
from src.domains.sms.ingest_router import router as ingest_router
from src.domains.sms.relation_reader import SmsRelationReader
from src.domains.sms.router import router as archive_router

register_relation_sms_reader(SmsRelationReader)
router = APIRouter()
router.include_router(ingest_router)
router.include_router(
    management_router,
    prefix="/sms",
    tags=["SMS"],
    dependencies=capability_dependencies(PlatformCapability.SMS),
)
router.include_router(archive_router)
