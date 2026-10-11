"""Native receipts expose the same issue taxonomy as the UI, never raw source debug values."""

from src.domains.plugins.schemas import PluginImportReport, PluginIssue


def _public_issue(issue: PluginIssue) -> PluginIssue:
    return issue.model_copy(update={"field": None, "detail": None})


def public_plugin_report(report: PluginImportReport) -> PluginImportReport:
    return report.model_copy(
        update={
            "components": [
                component.model_copy(
                    update={
                        "issues": [_public_issue(issue) for issue in component.issues],
                    }
                )
                for component in report.components
            ],
            "warnings": [_public_issue(issue) for issue in report.warnings],
        }
    )
