"""WP-09 visual candidate repair: validate, apply, verify, roll back."""

from .allowlist import (
    ALLOWED_OPS,
    rollback_ok,
    validate_materialized_roots,
    validate_plan,
)
from .answers import answers_preserved, collect_answers
from .execute import (
    RepairError,
    apply_plan,
    materialize_candidate,
    rollback_candidate,
    tree_digest,
)
from .recipes import RecipeError, affected_pages, bind_operation
from .regress import rerender_requirements, verify_candidate, verify_renders
from .rounds import MAX_ROUNDS, run_rounds
from .synthesize import PLAN_SCHEMA_VERSION, synthesize_plan
from .templates import (
    TemplateError,
    clear_templates,
    get_template,
    list_templates,
    register_template,
    verify_bindings,
)

__all__ = [
    "ALLOWED_OPS",
    "MAX_ROUNDS",
    "PLAN_SCHEMA_VERSION",
    "RecipeError",
    "RepairError",
    "TemplateError",
    "affected_pages",
    "answers_preserved",
    "apply_plan",
    "bind_operation",
    "clear_templates",
    "collect_answers",
    "get_template",
    "list_templates",
    "materialize_candidate",
    "register_template",
    "rerender_requirements",
    "rollback_candidate",
    "rollback_ok",
    "run_rounds",
    "synthesize_plan",
    "tree_digest",
    "validate_materialized_roots",
    "validate_plan",
    "verify_bindings",
    "verify_candidate",
    "verify_renders",
]
