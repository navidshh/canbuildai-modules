# HOT2000 Module

Self-contained inference application for selecting one representative HOT2000
file from 11 building characteristics. This folder contains only serving-time
code and artifacts; training, preprocessing, evaluation, and plotting outputs
are intentionally excluded.

## Structure

```text
app/                 FastAPI application, inference code, and templates
model/               Fitted preprocessor and K=1000 cluster centres
representatives/     Manifest, performance lookup, and 1,000 H2K/HSE files
scripts/             Reproducible representative-results exporter
runtime/downloads/   Temporary generated downloads
requirements.txt     Runtime Python dependencies
run.ps1              Windows setup and launch script
```

## Run on Windows

From this folder:

```powershell
.\run.ps1
```

Then open <http://127.0.0.1:8000>.

The first run creates `.venv` and installs the runtime dependencies. To use an
existing environment instead:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Optional environment variables `HOT2000_MODEL_DIR`, `HOT2000_H2K_DIR`,
`HOT2000_H2K_MANIFEST`, `HOT2000_RESULTS_PATH`, and
`HOT2000_DOWNLOADS_DIR` override the local paths.

## Representative results

After inference, the results page shows the precomputed performance of the
matched cluster representative. These values come from the same source row as
the downloadable HOT2000 file; the application does not run HOT2000 on demand.

For 520 ERS records, EUI is reported directly by the source data. For 480
records with missing or nonpositive source EUI, it is calculated as total
annual energy divided by modelled floor area. ERS-only fields are shown as
unavailable where the source data does not provide them.

Ten unavailable cluster representatives were replaced during deployment. The
exporter reads those delivered files' source rows from the full dataset so the
displayed results always describe the file offered for download.

To rebuild the display-safe lookup from the main repository artifacts:

```powershell
python scripts/export_representative_results.py
```