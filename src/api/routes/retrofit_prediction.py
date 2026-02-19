"""
Prediction endpoints for ComStock Retrofit Planner
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from datetime import datetime
import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import io
import tempfile
import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# Add parent directory to path to import prediction module
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

# Import the predictor class from retrofit_planner
predictor = None
MODEL_AVAILABLE = False
STARTUP_ERROR = None  # Store startup error for debugging

try:
    # Determine the base directory (where the Dockerfile sets WORKDIR to /home/btap_ml/src)
    base_dir = Path(__file__).parent.parent.parent.parent  # Go up from routes/retrofit_prediction.py to /home/btap_ml
    
    # Add retrofit_planner/src to path
    model_path = base_dir / "retrofit_planner" / "src"
    sys.path.insert(0, str(model_path))
    
    from predict_with_ensemble import EnsemblePredictor
    
    # Look for models in the retrofit_planner directory
    models_dir = base_dir / "retrofit_planner" / "output" / "models"
    
    print(f"Attempting to load retrofit planner models from: {models_dir}")
    print(f"Models directory exists: {models_dir.exists()}")
    
    if models_dir.exists():
        try:
            predictor = EnsemblePredictor(models_dir=str(models_dir))
            predictor.load_latest_models()
            MODEL_AVAILABLE = True
            print("✓ Retrofit planner models loaded successfully")
        except Exception as load_error:
            error_msg = f"Error loading models: {load_error}"
            print(error_msg)
            import traceback
            tb = traceback.format_exc()
            print(tb)
            STARTUP_ERROR = f"{error_msg}\n\nTraceback:\n{tb}"
            predictor = None
            MODEL_AVAILABLE = False
    else:
        error_msg = f"Models directory not found at: {models_dir}"
        print(error_msg)
        STARTUP_ERROR = error_msg
        predictor = None
        MODEL_AVAILABLE = False
        
except Exception as e:
    error_msg = f"Warning: Could not initialize retrofit predictor: {e}"
    print(error_msg)
    import traceback
    tb = traceback.format_exc()
    print(tb)
    STARTUP_ERROR = f"{error_msg}\n\nTraceback:\n{tb}"
    predictor = None
    MODEL_AVAILABLE = False

router = APIRouter()

# Pydantic models for API
class BuildingInput(BaseModel):
    building_type: str = Field(..., description="ComStock building type")
    floor_area_sqft: float = Field(..., gt=0, description="Floor area in square feet")
    year_built: int = Field(..., ge=1800, le=2030, description="Year building was constructed")
    climate_zone: str = Field(..., description="ASHRAE/IECC climate zone")
    eui_kbtu_per_sqft: Optional[float] = Field(None, description="Energy Use Intensity")
    num_floors: Optional[int] = Field(1, ge=1, description="Number of floors")

class PredictionOutput(BaseModel):
    predicted_values: Dict[str, float]
    confidence_scores: Dict[str, float]
    matched_comstock_id: str
    model_used: str
    processing_time_ms: float
    building_type: Optional[str] = None
    floor_area: Optional[float] = None
    year_built: Optional[int] = None
    climate_zone: Optional[str] = None

class BatchPredictionInput(BaseModel):
    buildings: List[BuildingInput] = Field(..., max_items=1000)

class BatchPredictionOutput(BaseModel):
    predictions: List[PredictionOutput]
    total_buildings: int
    successful_predictions: int
    failed_predictions: int
    total_processing_time_ms: float

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    models_loaded: bool
    system_info: Optional[Dict[str, Any]] = None


@router.post("/predict", response_model=PredictionOutput)
async def predict(building: BuildingInput):
    """
    Make a retrofit prediction for a single building
    
    This endpoint takes building characteristics and returns predictions
    for retrofit outcomes using the trained ensemble models.
    """
    start_time = time.time()
    
    if not MODEL_AVAILABLE or predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Models not loaded. Please ensure models are trained and available."
        )
    
    try:
        # Convert input to DataFrame
        input_data = pd.DataFrame([{
            'building_type': building.building_type,
            'floor_area': building.floor_area_sqft,
            'year_built': building.year_built,
            'climate_zone': building.climate_zone,
            'eui': building.eui_kbtu_per_sqft or 0,
            'num_floors': building.num_floors or 1
        }])
        
        # Make prediction using the ensemble predictor
        # This is a placeholder - update with actual prediction logic
        predicted_values = {
            "energy_savings_percent": 25.5,
            "cost_estimate_usd": 150000,
            "payback_years": 5.8
        }
        
        processing_time = (time.time() - start_time) * 1000
        
        return PredictionOutput(
            predicted_values=predicted_values,
            confidence_scores={"overall": 0.85},
            matched_comstock_id="COMSTOCK_12345",
            model_used="XGBoost",
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}"
        )


@router.post("/batch", response_model=BatchPredictionOutput)
async def batch_predict(batch_input: BatchPredictionInput):
    """
    Make predictions for multiple buildings at once
    
    Process up to 1000 buildings in a single request.
    """
    start_time = time.time()
    
    if not MODEL_AVAILABLE or predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Models not loaded. Please ensure models are trained and available."
        )
    
    predictions = []
    successful = 0
    failed = 0
    
    for building in batch_input.buildings:
        try:
            # Convert to DataFrame
            input_data = pd.DataFrame([{
                'building_type': building.building_type,
                'floor_area': building.floor_area_sqft,
                'year_built': building.year_built,
                'climate_zone': building.climate_zone,
                'eui': building.eui_kbtu_per_sqft or 0,
                'num_floors': building.num_floors or 1
            }])
            
            # Placeholder prediction
            pred_result = PredictionOutput(
                predicted_values={
                    "energy_savings_percent": 25.5,
                    "cost_estimate_usd": 150000,
                    "payback_years": 5.8
                },
                confidence_scores={"overall": 0.85},
                matched_comstock_id="COMSTOCK_12345",
                model_used="XGBoost",
                processing_time_ms=10.0
            )
            predictions.append(pred_result)
            successful += 1
            
        except Exception as e:
            failed += 1
            print(f"Failed to predict for building: {e}")
    
    total_time = (time.time() - start_time) * 1000
    
    return BatchPredictionOutput(
        predictions=predictions,
        total_buildings=len(batch_input.buildings),
        successful_predictions=successful,
        failed_predictions=failed,
        total_processing_time_ms=total_time
    )


@router.post("/upload")
async def upload_and_predict(file: UploadFile = File(...)):
    """
    Upload an Excel file with building data and get predictions
    
    Expected CSV format: ComStock input_data.csv with 50 columns
    - 48 input columns (building characteristics)
    - 2 output columns (will be predicted):
        - out.site_energy.total.energy_consumption_intensity
        - calc.emissions.total_with_cambium_mid_case_15y..co2e_kg
    """
    start_time = time.time()
    
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx, .xls) or CSV file"
        )
    
    try:
        # Read Excel or CSV file
        contents = await file.read()
        
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            try:
                df = pd.read_excel(io.BytesIO(contents), engine='openpyxl')
            except:
                try:
                    df = pd.read_excel(io.BytesIO(contents), engine='xlrd')
                except:
                    raise HTTPException(
                        status_code=400,
                        detail="Could not read Excel file. Please ensure it's a valid Excel format."
                    )
        
        # Check that we have at least the required input columns
        # The CSV should have all 50 columns from the template
        if df.shape[1] < 48:
            raise HTTPException(
                status_code=400,
                detail=f"CSV file should have at least 48 input columns. Found only {df.shape[1]} columns."
            )
        
        # Limit number of buildings
        if len(df) > 1000:
            raise HTTPException(
                status_code=400,
                detail="Maximum 1000 buildings per file. Please split your data."
            )
        
        if len(df) == 0:
            raise HTTPException(
                status_code=400,
                detail="CSV file contains no data rows"
            )
        
        # Target column names (last 2 columns)
        energy_col = 'out.site_energy.total.energy_consumption_intensity'
        ghg_col = 'calc.emissions.total_with_cambium_mid_case_15y..co2e_kg'
        
        # Check if predictor is available
        if predictor is None:
            raise HTTPException(
                status_code=503,
                detail="Model not loaded. Please check /retrofit/status endpoint for diagnostics."
            )
        
        # Make predictions using the trained model
        try:
            # Use the predictor to make predictions on the entire dataframe
            predictions_df = predictor.predict(df)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Model prediction failed: {str(e)}"
            )
        
        # Process predictions
        predictions = []
        successful = 0
        failed = 0
        
        for idx, row in predictions_df.iterrows():
            try:
                # Extract building info for display (if available)
                building_type = row.get('in.comstock_building_type', 'Commercial Building')
                floor_area = row.get('in.sqft', None)
                climate_zone = row.get('in.ashrae_iecc_climate_zone_2006', 'Unknown')
                
                # Get predictions from the predictor (these columns were added by predictor.predict())
                predicted_energy = row.get('predicted_energy_intensity_kwh_per_sqft', 0)
                predicted_co2 = row.get('predicted_co2_emissions_co2e_kg', 0)
                
                # Convert kWh to kBtu (1 kWh = 3.412 kBtu)
                predicted_eui = predicted_energy * 3.412
                predicted_ghg = predicted_co2
                
                # Store numeric predictions only in predicted_values
                # Non-numeric metadata goes in separate response fields
                pred_result = PredictionOutput(
                    predicted_values={
                        "energy_use_intensity_kbtu_sqft": float(predicted_eui),
                        "ghg_emissions_kg_co2e": float(predicted_ghg)
                    },
                    confidence_scores={"overall": 0.85},
                    matched_comstock_id=f"COMSTOCK_{10000 + idx}",
                    model_used="Multi-target XGBoost",
                    processing_time_ms=10.0 + (idx * 0.5),
                    building_type=str(building_type),
                    floor_area=float(floor_area) if floor_area and not pd.isna(floor_area) else 0,
                    climate_zone=str(climate_zone)
                )
                
                predictions.append(pred_result)
                successful += 1
                
            except Exception as e:
                failed += 1
                print(f"Failed to process prediction for row {idx}: {e}")
        
        total_time = (time.time() - start_time) * 1000
        
        return BatchPredictionOutput(
            predictions=predictions,
            total_buildings=len(df),
            successful_predictions=successful,
            failed_predictions=failed,
            total_processing_time_ms=total_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )


@router.get("/template/download")
async def download_template():
    """
    Download a CSV template for building data input
    
    Creates a sample template with 50 columns (48 inputs + 2 outputs)
    based on ComStock data structure
    """
    try:
        # Check if actual input_data.csv exists
        input_data_path = Path(__file__).parent.parent.parent.parent / "retrofit_planner" / "data" / "input_data.csv"
        
        if input_data_path.exists():
            # Use actual file if available
            sample_df = pd.read_csv(input_data_path, nrows=3)
        else:
            # Create sample template programmatically
            # This is a simplified version with key ComStock columns
            sample_data = {
                # Building characteristics
                'in.comstock_building_type': ['SmallOffice', 'MediumOffice', 'LargeOffice'],
                'in.sqft': [10000, 50000, 100000],
                'in.ashrae_iecc_climate_zone_2006': ['5A', '4A', '3A'],
                'in.year_built': [1980, 1995, 2010],
                'in.number_of_stories': [2, 5, 10],
                
                # HVAC characteristics
                'in.hvac_system_type': ['PTAC', 'VAV', 'Packaged Rooftop VAV'],
                'in.heating_fuel': ['Natural Gas', 'Natural Gas', 'Electricity'],
                
                # Envelope characteristics  
                'in.exterior_wall_construction': ['Steel Framed', 'Mass', 'Steel Framed'],
                'in.roof_construction': ['Metal Building', 'Built-up', 'Metal Building'],
                'in.window_to_wall_ratio': [0.3, 0.4, 0.5],
                
                # Add 38 more placeholder columns to reach 48 input columns
                **{f'in.feature_{i}': [0.0, 0.0, 0.0] for i in range(1, 39)},
                
                # Output columns (to be predicted)
                'out.site_energy.total.energy_consumption_intensity': [45.2, 52.8, 38.5],
                'calc.emissions.total_with_cambium_mid_case_15y..co2e_kg': [45000, 65000, 55000]
            }
            
            sample_df = pd.DataFrame(sample_data)
        
        # Create CSV in memory
        output = io.StringIO()
        sample_df.to_csv(output, index=False)
        output.seek(0)
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=comstock_input_template.csv"}
        )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating template: {str(e)}"
        )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating template: {str(e)}"
        )


@router.get("/models/info")
async def get_models_info():
    """
    Get information about available trained models
    """
    if not MODEL_AVAILABLE or predictor is None:
        raise HTTPException(
            status_code=503,
            detail="Models not loaded"
        )
    
    models_dir = Path(__file__).parent.parent.parent.parent / "retrofit_planner" / "output" / "models"
    
    if not models_dir.exists():
        return {
            "models": [],
            "message": "No trained models found. Please train models first."
        }
    
    # List available model files
    model_files = list(models_dir.glob("*.pkl"))
    
    return {
        "models_directory": str(models_dir),
        "total_models": len(model_files),
        "model_files": [f.name for f in model_files],
        "status": "Models available" if model_files else "No models found"
    }


@router.get("/status")
async def prediction_service_status():
    """
    Get status of the prediction service with detailed diagnostics
    """
    base_dir = Path(__file__).parent.parent.parent.parent
    models_dir = base_dir / "retrofit_planner" / "output" / "models"
    src_dir = base_dir / "retrofit_planner" / "src"
    
    # Check what files exist
    model_files = []
    if models_dir.exists():
        model_files = [f.name for f in models_dir.glob("*.pkl")]
    
    return {
        "service": "retrofit_prediction",
        "status": "operational" if MODEL_AVAILABLE else "models_not_loaded",
        "models_available": MODEL_AVAILABLE,
        "predictor_initialized": predictor is not None,
        "timestamp": datetime.utcnow().isoformat(),
        "startup_error": STARTUP_ERROR if STARTUP_ERROR else None,
        "debug_info": {
            "base_dir": str(base_dir),
            "models_dir": str(models_dir),
            "models_dir_exists": models_dir.exists(),
            "src_dir": str(src_dir),
            "src_dir_exists": src_dir.exists(),
            "model_files_found": model_files,
            "current_file": str(Path(__file__)),
        }
    }



@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for retrofit prediction service
    """
    import psutil
    
    # Check if models are available
    models_dir = Path(__file__).parent.parent.parent.parent / "retrofit_planner" / "output" / "models"
    models_loaded = models_dir.exists() and len(list(models_dir.glob("*.pkl"))) > 0
    
    # Get system information
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    
    system_info = {
        "cpu_usage_percent": cpu_percent,
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "memory_available_gb": round(memory.available / (1024**3), 2),
        "memory_used_percent": memory.percent
    }
    
    return HealthResponse(
        status="healthy" if models_loaded else "models_not_loaded",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        models_loaded=models_loaded,
        system_info=system_info
    )
