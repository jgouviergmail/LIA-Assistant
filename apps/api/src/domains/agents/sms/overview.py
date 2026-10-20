"""Keep 360-degree SMS in the same registry, token projection and live proof."""

from uuid import UUID

from src.domains.agents.sms.model_output import SmsModelToolOutput
from src.domains.agents.sms.projection import project_page
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.sms_tools import sms_output
from src.domains.relations.overview import OverviewEvidence
from src.domains.sms.read_schemas import SmsPage, SmsView


def overview_output(
    payload: dict[str, object], evidence: OverviewEvidence, owner: UUID, message: str
) -> UnifiedToolOutput:
    proof = evidence.detail.sms_proof
    if "sms" not in payload or proof is None:
        return UnifiedToolOutput.data_success(message=message, structured_data=payload)
    page = project_page(
        SmsPage(
            items=[SmsView.model_validate(item.model_dump()) for item in evidence.detail.sms[:1]],
            total=evidence.detail.sms_total,
            as_of=proof.as_of,
            revision=proof.revision,
        ),
        owner=owner,
    )
    source = sms_output(page, "get_person_overview_tool")
    selected = dict(payload)
    selected.pop("sms", None)
    selected.pop("sms_total", None)
    selected["sms_archive"] = page.model_dump(mode="json")
    return SmsModelToolOutput.data_success(
        message=message,
        structured_data=selected,
        registry_updates=source.registry_updates,
        metadata=source.metadata,
    )
