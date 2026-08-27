"""Export display-ready performance results for deployed representatives."""

from argparse import ArgumentParser
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    MODULE_ROOT.parent
    / "results-gpu"
    / "clustering-1000"
    / "kmeans_closest_to_centroids.csv"
)
DEFAULT_RAW_SOURCE = (
    MODULE_ROOT.parent
    / "data"
    / "final"
    / "combined_raw_with_evaluationnum.csv"
)
DEFAULT_OUTPUT = MODULE_ROOT / "representatives" / "results.csv"

REPLACEMENT_EVALUATION_IDS = {
    55: 1043297,
    254: 1335246,
    372: 1158767,
    373: 492224,
    414: 504945,
    425: 1641709,
    562: 1499390,
    621: 484985,
    730: 1847831,
    744: 799797,
}

SOURCE_COLUMNS = {
    "cluster": "cluster",
    "YEARBUILT": "year_built",
    "AIR50P": "air_leakage_ach_50pa",
    "ERSENERGYINTENSITY": "eui_gj_m2_year",
    "ERSRATING": "ers_rating_gj_year",
    "ERSGHG": "ghg_tonnes_year",
    "EGHFCONTOTAL": "annual_energy_gj",
    "EGHSPACEENERGY": "space_heating_gj",
    "ERSWATERHEATINGENERGY": "water_heating_gj",
    "ERSVENTILATIONENERGY": "ventilation_gj",
    "ERSSPACECOOLENERGY": "space_cooling_gj",
    "EGHDESHTLOSS": "design_heat_loss_kw",
    "EGHHLWALLS": "wall_heat_loss_gj",
    "EGHHLCEILING": "ceiling_heat_loss_gj",
    "EGHHLFOUND": "foundation_heat_loss_gj",
    "EGHHLWINDOOR": "windows_doors_heat_loss_gj",
    "EGHHLAIR": "air_leakage_heat_loss_gj",
}

MJ_COLUMNS = {
    "annual_energy_gj",
    "space_heating_gj",
    "water_heating_gj",
    "ventilation_gj",
    "space_cooling_gj",
    "wall_heat_loss_gj",
    "ceiling_heat_loss_gj",
    "foundation_heat_loss_gj",
    "windows_doors_heat_loss_gj",
    "air_leakage_heat_loss_gj",
}


def _replacement_rows(raw_source_path: Path, columns: list[str]) -> pd.DataFrame:
    evaluation_ids = set(REPLACEMENT_EVALUATION_IDS.values())
    matches = []
    for chunk in pd.read_csv(
        raw_source_path,
        usecols=["EVALUATIONSID", *columns],
        chunksize=100_000,
        low_memory=False,
    ):
        matched = chunk[chunk["EVALUATIONSID"].isin(evaluation_ids)]
        if not matched.empty:
            matches.append(matched)

    if not matches:
        raise ValueError("No replacement performance rows were found")

    replacements = pd.concat(matches).drop_duplicates("EVALUATIONSID")
    replacements = replacements.set_index("EVALUATIONSID")
    missing = evaluation_ids.difference(replacements.index)
    if missing:
        raise ValueError(f"Missing replacement evaluation IDs: {sorted(missing)}")
    return replacements


def export_results(
    source_path: Path,
    raw_source_path: Path,
    output_path: Path,
) -> pd.DataFrame:
    """Create one display-safe performance record per model cluster."""
    metric_columns = [column for column in SOURCE_COLUMNS if column != "cluster"]
    required = ["cluster", *metric_columns, "FLOORAREA", "HEATEDFLOORAREA"]
    source = pd.read_csv(source_path, usecols=required, low_memory=False)
    replacement_rows = _replacement_rows(
        raw_source_path, [*metric_columns, "FLOORAREA", "HEATEDFLOORAREA"]
    )
    for cluster, evaluation_id in REPLACEMENT_EVALUATION_IDS.items():
        source.loc[source["cluster"] == cluster, required[1:]] = (
            replacement_rows.loc[evaluation_id, required[1:]].to_numpy()
        )

    results = source[list(SOURCE_COLUMNS)].rename(columns=SOURCE_COLUMNS)

    floor_area = source["HEATEDFLOORAREA"].where(
        source["HEATEDFLOORAREA"] > 0, source["FLOORAREA"]
    )
    recorded_eui = results["eui_gj_m2_year"] > 0
    results["eui_source"] = np.where(recorded_eui, "reported", "calculated")
    results["eui_gj_m2_year"] = results["eui_gj_m2_year"].where(
        recorded_eui,
        source["EGHFCONTOTAL"] / floor_area / 1000
    )
    results["floor_area_m2"] = floor_area

    for column in MJ_COLUMNS:
        results[column] = results[column] / 1000
    results["design_heat_loss_kw"] = results["design_heat_loss_kw"] / 1000

    results = results[
        [
            "cluster",
            "eui_gj_m2_year",
            "eui_source",
            "annual_energy_gj",
            "ers_rating_gj_year",
            "ghg_tonnes_year",
            "space_heating_gj",
            "water_heating_gj",
            "ventilation_gj",
            "space_cooling_gj",
            "design_heat_loss_kw",
            "wall_heat_loss_gj",
            "ceiling_heat_loss_gj",
            "foundation_heat_loss_gj",
            "windows_doors_heat_loss_gj",
            "air_leakage_heat_loss_gj",
            "floor_area_m2",
            "year_built",
            "air_leakage_ach_50pa",
        ]
    ].sort_values("cluster")

    if len(results) != 1000 or set(results["cluster"]) != set(range(1000)):
        raise ValueError("Results must contain exactly clusters 0 through 999")
    if results["eui_gj_m2_year"].isna().any():
        raise ValueError("Every representative must have a reported or calculated EUI")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_path, index=False, float_format="%.4f")
    return results


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--raw-source", type=Path, default=DEFAULT_RAW_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    results = export_results(args.source, args.raw_source, args.output)
    source_counts = results["eui_source"].value_counts()
    print(f"Wrote {len(results)} representative results to {args.output}")
    print(f"Reported EUI: {source_counts.get('reported', 0)}")
    print(f"Calculated EUI: {source_counts.get('calculated', 0)}")


if __name__ == "__main__":
    main()