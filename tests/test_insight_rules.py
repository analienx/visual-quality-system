"""Rule tests: insight duplication (INS-01) and chart practice (CHT-01/02)."""
from pathlib import Path

from vqs.design_rules import decomposition_tree_dimensions, insight_no_duplicate_grain, map_location_binding

SALES = "Fact Sales.Revenue"
REGION = "Dim Store.Region"
CHANNEL = "Dim Store.Channel"
CATEGORY = "Dim Product.Category"


def _grain(page, visual, vtype, measures, dimensions, filtered=0):
    return {"page": page, "visual": visual, "type": vtype,
            "measures": list(measures), "dimensions": list(dimensions),
            "valued_filters": filtered}


def test_contained_grain_fails_map_inside_tree() -> None:
    """The Deep-dive case: map Sales x Region inside tree Sales x Region+Category."""
    result = insight_no_duplicate_grain([
        _grain("P1", "sales-by-region", "map", [SALES], [REGION]),
        _grain("P1", "what-drives-sales", "decompositionTreeVisual",
               [SALES], [REGION, CATEGORY]),
        _grain("P1", "sales-by-channel", "donutChart", [SALES], [CHANNEL])])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"] == [{
        "kind": "contained_grain", "page": "P1",
        "visuals": ["sales-by-region", "what-drives-sales"],
        "types": ["decompositionTreeVisual", "map"],
        "measures": [SALES], "dimensions": [CATEGORY, REGION]}]


def test_twin_cards_same_grain_fail() -> None:
    result = insight_no_duplicate_grain([
        _grain("P1", "card-a", "card", [SALES], []),
        _grain("P1", "card-b", "card", [SALES], [])])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"][0]["kind"] == "same_grain"


def test_card_and_breakdown_pass() -> None:
    """A total beside its breakdown is coherence, not duplication."""
    result = insight_no_duplicate_grain([
        _grain("P1", "cardx", "card", [SALES], []),
        _grain("P1", "chart", "columnChart", [SALES], [REGION])])
    assert result["status"] == "pass"


def test_valued_filters_skip_pair() -> None:
    result = insight_no_duplicate_grain([
        _grain("P1", "card-a", "card", [SALES], []),
        _grain("P1", "card-b", "card", [SALES], [], filtered=1)])
    assert result["status"] == "pass"
    assert result["evidence"]["skipped_filtered_pairs"] == 1


def test_cross_page_pairs_ignored() -> None:
    result = insight_no_duplicate_grain([
        _grain("P1", "card-a", "card", [SALES], []),
        _grain("P2", "card-b", "card", [SALES], [])])
    assert result["status"] == "pass"
    assert result["evidence"]["pairs_compared"] == 0


def test_grain_unknown_on_missing_or_invalid() -> None:
    assert insight_no_duplicate_grain(None)["status"] == "unknown"
    assert insight_no_duplicate_grain([])["status"] == "unknown"
    assert insight_no_duplicate_grain([{"page": "P1"}])["status"] == "unknown"


def test_tree_two_dimensions_pass() -> None:
    result = decomposition_tree_dimensions([{
        "page": "P1", "visual": "treevis", "analyze": [SALES],
        "explain_by": [REGION, CATEGORY], "unrecognized_roles": False}])
    assert result["status"] == "pass"


def test_tree_single_dimension_fails() -> None:
    result = decomposition_tree_dimensions([{
        "page": "P2", "visual": "thintree", "analyze": [SALES],
        "explain_by": [REGION], "unrecognized_roles": False}])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"] == [{
        "kind": "too_few_dimensions", "page": "P2", "visual": "thintree",
        "distinct_dimensions": 1}]


def test_tree_duplicate_and_missing_analyze_fail() -> None:
    result = decomposition_tree_dimensions([
        {"page": "P1", "visual": "dup", "analyze": [SALES],
         "explain_by": [REGION, REGION, CATEGORY],
         "unrecognized_roles": False},
        {"page": "P1", "visual": "empty", "analyze": [],
         "explain_by": [REGION, CATEGORY], "unrecognized_roles": False}])
    kinds = [c["kind"] for c in result["evidence"]["conflicts"]]
    assert result["status"] == "fail"
    assert kinds == ["duplicate_dimension", "missing_analyze"]


def test_tree_unrecognized_roles_unknown() -> None:
    result = decomposition_tree_dimensions([{
        "page": "P1", "visual": "odd", "analyze": [], "explain_by": [],
        "unrecognized_roles": True}])
    assert result["status"] == "unknown"
    assert decomposition_tree_dimensions([])["status"] == "unknown"


def test_map_geo_pass_non_geo_fail() -> None:
    good = map_location_binding([{
        "page": "P1", "visual": "geomap", "type": "map",
        "locations": ["Dim Store.Country"],
        "categories": {"Dim Store.Country": "Country"}}])
    assert good["status"] == "pass"
    bad = map_location_binding([{
        "page": "P1", "visual": "urlmap", "type": "filledMap",
        "locations": ["Dim Store.Photo"],
        "categories": {"Dim Store.Photo": "ImageUrl"}}])
    assert bad["status"] == "fail"
    assert bad["evidence"]["conflicts"][0]["kind"] == "non_geographic_binding"


def test_map_without_location_fails() -> None:
    result = map_location_binding([{
        "page": "P2", "visual": "lostmap", "type": "map",
        "locations": [], "categories": {}}])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"][0]["kind"] == "no_location_field"


def test_map_uncategorized_unknown() -> None:
    result = map_location_binding([{
        "page": "P1", "visual": "mapvis", "type": "map",
        "locations": [REGION], "categories": {REGION: None}}])
    assert result["status"] == "unknown"
    assert map_location_binding([])["status"] == "unknown"


def test_pipeline_runs_new_rules(tmp_path: Path) -> None:
    from vqs.pipeline import run_check
    facts = {"rules": {
        "insight.no_duplicate_grain": {"visuals": [
            _grain("P1", "a", "card", [SALES], []),
            _grain("P1", "b", "card", [SALES], [])]},
        "chart.decomposition_tree_dimensions": {"trees": [
            {"page": "P1", "visual": "t", "analyze": [SALES],
             "explain_by": [REGION, CATEGORY],
             "unrecognized_roles": False}]}}}
    result = run_check(facts, tmp_path, run_id="insight-pipeline")
    assert result["verdict"] == "fail"
    assert {f["check"] for f in result["findings"]} == {
        "insight.no_duplicate_grain", "chart.decomposition_tree_dimensions"}

def test_same_grain_dimensioned_twins_fail() -> None:
    result = insight_no_duplicate_grain([
        _grain("P1", "chart-a", "columnChart", [SALES], [REGION]),
        _grain("P1", "chart-b", "barChart", [SALES], [REGION])])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"][0]["kind"] == "same_grain"


def test_contained_grain_is_order_independent() -> None:
    pair = [[SALES], [REGION, CATEGORY]]
    flipped = insight_no_duplicate_grain([
        _grain("P1", "tree", "decompositionTreeVisual", *pair),
        _grain("P1", "map", "map", [SALES], [REGION])])
    assert flipped["status"] == "fail"
    assert flipped["evidence"]["conflicts"][0]["kind"] == "contained_grain"


def test_tree_fail_survives_unrecognized_sibling() -> None:
    result = decomposition_tree_dimensions([
        {"page": "P1", "visual": "thin", "analyze": [SALES],
         "explain_by": [REGION], "unrecognized_roles": False},
        {"page": "P1", "visual": "odd", "analyze": [], "explain_by": [],
         "unrecognized_roles": True}])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"][0]["kind"] == "too_few_dimensions"
    assert result["evidence"]["unverified"] == ["P1/odd"]


def test_map_fail_needs_every_column_non_geographic() -> None:
    mixed = map_location_binding([{
        "page": "P1", "visual": "map", "type": "map",
        "locations": [REGION, "Dim Store.Photo"],
        "categories": {REGION: None, "Dim Store.Photo": "ImageUrl"}}])
    assert mixed["status"] == "unknown"
    geo = map_location_binding([{
        "page": "P1", "visual": "map", "type": "map",
        "locations": [REGION, "Dim Store.Country"],
        "categories": {REGION: "ImageUrl", "Dim Store.Country": "Country"}}])
    assert geo["status"] == "pass"
    empty_cat = map_location_binding([{
        "page": "P1", "visual": "map", "type": "map",
        "locations": [REGION], "categories": {REGION: ""}}])
    assert empty_cat["status"] == "unknown"
    all_bad = map_location_binding([{
        "page": "P1", "visual": "map", "type": "map",
        "locations": [REGION, "Dim Store.Photo"],
        "categories": {REGION: "WebUrl", "Dim Store.Photo": "ImageUrl"}}])
    assert all_bad["status"] == "fail"


def test_unhashable_and_untyped_elements_are_unknown() -> None:
    assert map_location_binding([{
        "page": "P1", "visual": "map", "type": "map",
        "locations": [["nested"]], "categories": {}}])["status"] == "unknown"
    assert decomposition_tree_dimensions([{
        "page": "P1", "visual": "t", "analyze": [5],
        "explain_by": [], "unrecognized_roles": False}])["status"] == "unknown"

def test_cross_page_same_grain_fails() -> None:
    from vqs.design_rules import insight_no_cross_page_duplicate_grain
    result = insight_no_cross_page_duplicate_grain([
        _grain("P1", "chart-a", "columnChart", [SALES], [REGION]),
        _grain("P2", "chart-b", "barChart", [SALES], [REGION])])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"] == [{
        "kind": "same_grain", "pages": ["P1", "P2"],
        "visuals": ["P1/chart-a", "P2/chart-b"],
        "types": ["barChart", "columnChart"],
        "measures": [SALES], "dimensions": [REGION]}]


def test_cross_page_cards_and_same_page_pass() -> None:
    from vqs.design_rules import insight_no_cross_page_duplicate_grain
    cards = insight_no_cross_page_duplicate_grain([
        _grain("P1", "card-a", "card", [SALES], []),
        _grain("P2", "card-b", "card", [SALES], [])])
    assert cards["status"] == "pass"
    same_page = insight_no_cross_page_duplicate_grain([
        _grain("P1", "a", "card", [SALES], []),
        _grain("P1", "b", "card", [SALES], [])])
    assert same_page["status"] == "pass"
    assert same_page["evidence"]["pairs_compared"] == 0
    assert insight_no_cross_page_duplicate_grain([])["status"] == "unknown"


def test_cross_page_contained_grain_fails() -> None:
    from vqs.design_rules import insight_no_cross_page_duplicate_grain
    result = insight_no_cross_page_duplicate_grain([
        _grain("P1", "tree", "decompositionTreeVisual",
               [SALES], [REGION, CATEGORY]),
        _grain("P2", "map", "map", [SALES], [REGION])])
    assert result["status"] == "fail"
    assert result["evidence"]["conflicts"][0]["kind"] == "contained_grain"
