"""Microsoft-guided report authoring route (R6-E07).

VQS repairs stay candidate-only typed file writes; this package routes
their validation through Microsoft's ``powerbi-report-author``
executable (documented distribution channel
``@microsoft/powerbi-report-authoring-cli``) when the caller selects
it, with an explicit recorded fallback to the direct writer. Schema
validation is never Desktop or render approval — that limit is
recorded in every authoring record.
"""
from .adapter import POLICIES, direct_record, run_backend, select
from .mscli import PACKAGE_NAME, TOOL_NAME, probe, validate

__all__ = ["PACKAGE_NAME", "POLICIES", "TOOL_NAME", "direct_record",
           "probe", "run_backend", "select", "validate"]
