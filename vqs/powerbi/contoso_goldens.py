"""Independent, frozen query fingerprints for the approved Contoso G1/G4 oracle.

These are reviewed DAX query-text digests (UTF-8, no normalization), not
recalculated from the live query generator. Changing a query requires
separately reviewing the semantic meaning and consciously updating this
reference before a release. These hashes do not prove Desktop loaded bytes.
"""
from __future__ import annotations

PINNED_DAX_SHA256: dict[int | None, dict[str, str]] = {
    None: {
        "country": "392d2b0910a488713e035758197d6437f87915081756805c1e0c7adc5ff6faee",
        "region": "6e22a9d49c7f315c4414c0faa3bf7455bcfd2ec559d724bd7a921a2e50013e43",
        "kpis": "2193f84ed8fcbe2e349f49462308795a335a9f14e4e37a5f4f6817857192c711",
    },
    2023: {
        "country": "74d7aab20d271c0adb4d4e9ba91d30a93253ddb7bcf5fc12800fb8399fde29b0",
        "region": "b3098e22af4181500f34099a356bb4461f638d6083e22a302585c76de935c235",
        "kpis": "629ff1801fa09dd36d3f6bf79300abb239257215168976d2fb98616d7e1e3ce9",
    },
    2024: {
        "country": "33bada8b831a1ca177c3a9fd83eaaf3f0efad1314c893196641ef71afe7bd9a1",
        "region": "89ae7e486d30116b67aa69b1320e94e46954c99ccf87cb2e3f61a3f0b2750562",
        "kpis": "b6b2d43aa037f2d1dde722182c5564e7cd3d864550d58d8f75e16aabe029177f",
    },
    2025: {
        "country": "0f76c0b47030d646be2aaa47475825b6d9be56dcde48620154dd00d070dcb2c6",
        "region": "7b0e7242067564a9a8dc61ddbad09ab6896058481c6a6f132a11364f699f6536",
        "kpis": "0193ead7fba5b6a77137af61f3d357810b5ea80a2aec01c3233180ebc90cf914",
    },
}

# Explicit 2024+Europe 4-KPI DAX reviewed independently of runtime query builder.
PINNED_REGION_EUROPE_2024_SHA256 = "107780d0056bea95a19eec4416fdbf16bd1e77c9e42b460420659ed5f1fee381"
