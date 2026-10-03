# Template authoring contract (post-repair milestone)

**Status:** contract definition, not an implementation. Authoring builds
only on a merged, independently verified visual-repair milestone
(WP-09, candidate [PR #29](https://github.com/analienx/visual-quality-system/pull/29));
no authoring code ships in this snapshot. Broader DAX/model mutation
stays a later, separately authorized capability and is explicitly out
of this contract.

## 1. What authoring is

Instantiating a new visual from a vetted, version-pinned template into
a disposable candidate report: the same `validate → apply → verify →
rollback` shape as repair, with one extra input — an owner-confirmed
analytical question the new visual must answer. Authoring never edits
the original report, the semantic model, or any DAX/RLS object.

## 2. Inputs (all required, all source-bound)

| Input | Source | Rule |
| --- | --- | --- |
| Owner-confirmed question + oracle ID | owner, recorded | no question, no visual; inferred tasks are refused |
| Actual model facts | TMDL source or Modeling MCP `Ready` measures | field refs must exist; `Validate` syntax alone proves nothing |
| Vetted template body | real captured `visual.json` + capture provenance | fabricated bodies are evidence fabrication; registration is a reviewed act |
| Required bindings | template declaration | every `queryRef` must resolve on the target; missing bindings refuse |

## 3. Registry rules (mechanism: `vqs/repair/templates.py` in PR #29)

- Register `(name, version, visual_type, body, required_bindings,
  oracle_id)`; shape, finiteness, and size checks reject malformed
  bodies at registration time.
- Nothing ships preloaded: an empty registry blocks every authoring
  request until a reviewed registration lands.
- Fetch returns a copy; callers cannot mutate registered state.
- Versions are immutable: a changed body registers under a new
  version, never by silent overwrite.

## 4. Instantiation gates (each must pass)

1. Plan validation: typed op, declared write targets inside a fresh
   disposable candidate, realpath overlap/link/hardlink refusal,
   mandatory rollback recipe.
2. Binding verification: `verify_bindings` proves every required
   `queryRef` present on the target visual's query.
3. Intent gate: `identical_intent` or an owner-approved semantic
   change id; anything else blocks.
4. Answer preservation (`answers_preserved` + `collect_answers`,
   GOAL 14): the candidate reproduces the original scoped answers
   within declared tolerance; missing or divergent rows block or
   fail, never pass.
5. Regression: untouched files byte-identical, touched files differ
   only at declared paths, IDs intact, every visual finite and
   in-canvas, neighbors included.
6. Rerender: fresh complete renders cover affected pages plus order
   neighbors before any approval; shared presentation changes
   invalidate all pages.

## 5. Explicit non-goals

Generalized multi-page authoring, new measures/dimensions, DAX
rewrites, RLS changes, forecast/domain packs, and any model mutation.
Each needs its own work package, owner authorization, and independent
verification; this contract must not be stretched to cover them.

## 6. Milestone acceptance (before any promotion)

Two unrelated domain fixtures authored end to end; negatives for
unverified bindings, missing oracle, intent change without approval,
answer drift, and cropped neighbors; bounded retries (≤3) with
fingerprint/invariant stops; independent reviewer reproduces the
renders and inspects the diffs; owner approves promotion. Partial
success is never called a release.
