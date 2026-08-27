"""FastAPI application for selecting representative HOT2000 files."""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
import shutil

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator

from .config import (
    DOWNLOADS_DIR,
    FRONTEND_URL,
    MANIFEST_PATH,
    REPRESENTATIVES_DIR,
    RESULTS_PATH,
)
from .prediction import predict_cluster


app = FastAPI(title="HOT2000 Representative Model API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://main.d2hvpyy9rpvb37.amplifyapp.com",
        "http://localhost:8080",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


class BuildingInput(BaseModel):
    houseregion: str = Field(min_length=1)
    clientpcode: str = Field(min_length=3, max_length=7)
    typeofhouse: str = Field(min_length=1)
    storeys: str = Field(min_length=1)
    footprint: float = Field(gt=0)
    fndtype: str = Field(min_length=1)
    furnacefuel: str = Field(min_length=1)
    furnacetype: str = Field(min_length=1)
    pdhwfuel: str = Field(min_length=1)
    pdhwtype: str = Field(min_length=1)
    aircondtype: str = Field(min_length=1)

    @field_validator("clientpcode")
    @classmethod
    def normalize_postal_code(cls, value: str) -> str:
        return value.strip().upper()[:3]


@app.get("/health")
def health():
    return {"status": "ok", "service": "hot2000"}


@lru_cache(maxsize=1)
def _manifest() -> pd.DataFrame:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"HOT2000 manifest not found: {MANIFEST_PATH}")

    manifest = pd.read_csv(MANIFEST_PATH)
    required_columns = {"cluster", "filename"}
    missing_columns = required_columns.difference(manifest.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"HOT2000 manifest is missing columns: {missing}")

    manifest = manifest[["cluster", "filename"]].copy()
    manifest["cluster"] = manifest["cluster"].astype(int)
    return manifest


@lru_cache(maxsize=1)
def _representative_results() -> pd.DataFrame:
    if not RESULTS_PATH.is_file():
        raise FileNotFoundError(
            f"HOT2000 representative results not found: {RESULTS_PATH}"
        )

    results = pd.read_csv(RESULTS_PATH)
    required_columns = {
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
    }
    missing_columns = required_columns.difference(results.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"HOT2000 results are missing columns: {missing}")

    results["cluster"] = results["cluster"].astype(int)
    if results["cluster"].duplicated().any():
        raise ValueError("HOT2000 results contain duplicate clusters")
    return results.set_index("cluster")


def _cleanup_downloads() -> None:
    for extension in ("*.h2k", "*.hse"):
        for file_path in DOWNLOADS_DIR.glob(extension):
            file_path.unlink(missing_ok=True)


def _representative_for_cluster(cluster: int) -> Path:
    match = _manifest()[lambda rows: rows["cluster"] == cluster]
    if match.empty:
        raise FileNotFoundError(
            f"No representative HOT2000 file mapped for cluster {cluster}"
        )

    filename = str(match.iloc[0]["filename"])
    if Path(filename).name != filename or Path(filename).suffix.lower() not in {
        ".h2k",
        ".hse",
    }:
        raise ValueError(f"Invalid HOT2000 filename in manifest: {filename}")

    source_path = REPRESENTATIVES_DIR / filename
    if not source_path.is_file():
        raise FileNotFoundError(f"HOT2000 source file not found: {source_path}")
    return source_path


def _metric(row, column, label, unit, decimals=1):
    value = row[column]
    available = not pd.isna(value)
    return {
        "label": label,
        "value": f"{value:,.{decimals}f}" if available else "Not available",
        "unit": unit if available else "",
        "available": available,
    }


def _results_context(cluster: int) -> dict:
    results = _representative_results()
    if cluster not in results.index:
        raise FileNotFoundError(
            f"No precomputed results mapped for cluster {cluster}"
        )

    row = results.loc[cluster]
    return {
        "eui": _metric(
            row, "eui_gj_m2_year", "Energy use intensity", "GJ/m²/year", 2
        ),
        "eui_source": str(row["eui_source"]),
        "summary_metrics": [
            _metric(row, "annual_energy_gj", "Annual energy use", "GJ/year"),
            _metric(row, "ghg_tonnes_year", "GHG emissions", "t CO₂e/year"),
            _metric(row, "design_heat_loss_kw", "Design heat loss", "kW"),
        ],
        "building_metrics": [
            _metric(row, "floor_area_m2", "Modelled floor area", "m²"),
            _metric(row, "year_built", "Year built", "", 0),
            _metric(
                row,
                "air_leakage_ach_50pa",
                "Air leakage at 50 Pa",
                "ACH",
                2,
            ),
            _metric(
                row,
                "ers_rating_gj_year",
                "EnerGuide rating",
                "GJ/year",
            ),
        ],
        "energy_metrics": [
            _metric(row, "space_heating_gj", "Space heating", "GJ/year"),
            _metric(row, "water_heating_gj", "Water heating", "GJ/year"),
            _metric(row, "ventilation_gj", "Ventilation", "GJ/year"),
            _metric(row, "space_cooling_gj", "Space cooling", "GJ/year"),
        ],
        "heat_loss_metrics": [
            _metric(row, "wall_heat_loss_gj", "Walls", "GJ/year"),
            _metric(row, "ceiling_heat_loss_gj", "Ceiling", "GJ/year"),
            _metric(row, "foundation_heat_loss_gj", "Foundation", "GJ/year"),
            _metric(
                row,
                "windows_doors_heat_loss_gj",
                "Windows and doors",
                "GJ/year",
            ),
            _metric(
                row,
                "air_leakage_heat_loss_gj",
                "Air leakage",
                "GJ/year",
            ),
        ],
    }


def _download_path(filename: str) -> Path:
    if Path(filename).name != filename or Path(filename).suffix.lower() not in {
        ".h2k",
        ".hse",
    }:
        raise HTTPException(status_code=400, detail="Invalid download filename")
    return DOWNLOADS_DIR / filename


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(FRONTEND_URL, status_code=307)


@app.post("/api/predict")
def predict(building: BuildingInput):
    _cleanup_downloads()
    building_data = {
        "HOUSEREGION": building.houseregion,
        "CLIENTPCODE": building.clientpcode,
        "TYPEOFHOUSE": building.typeofhouse,
        "STOREYS": building.storeys,
        "FOOTPRINT": building.footprint,
        "FNDTYPE": building.fndtype,
        "FURNACEFUEL": building.furnacefuel,
        "FURNACETYPE": building.furnacetype,
        "PDHWFUEL": building.pdhwfuel,
        "PDHWTYPE": building.pdhwtype,
        "AIRCONDTYPE": building.aircondtype,
    }

    try:
        cluster = predict_cluster(building_data)
        source_path = _representative_for_cluster(cluster)
        result_context = _results_context(cluster)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    filename = f"house_{datetime.now():%Y%m%d_%H%M%S}{source_path.suffix.lower()}"
    shutil.copy2(source_path, _download_path(filename))
    return {
        "cluster": cluster,
        "filename": filename,
        "download_path": f"/download_file/{filename}",
        **result_context,
    }


@app.get("/download_file/{filename}")
async def download_file(filename: str):
    file_path = _download_path(filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Download not found")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )