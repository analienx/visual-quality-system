"""Microsoft-guided report authoring route (R6-E07).

VQS repairs stay candidate-only typed file writes; this package routes
their validation through Microsoft's ``powerbi-report-author`` CLI
when the caller selects it, with an explicit recorded fallback to
the direct writer. Schema validation is never Desktop or render
approval — that limit is recorded in every authoring record.
"""
from .adapter import POLICIES, direct_record, run_backend, select
from .mscli import TOOL_NAME, probe, validate

__all__ = ["POLICIES", "TOOL_NAME", "direct_record", "probe",
           "run_backend", "select", "validate"]
