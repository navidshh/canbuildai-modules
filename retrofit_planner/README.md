# Retrofit Planner - Trained Models and Prediction

This directory contains only the essential files needed for the Retrofit Planner API:

## Structure

```
retrofit_planner/
├── data/
│   └── input_data.csv          # Sample template for user input
├── output/
│   └── models/
│       ├── best_model_multitarget_XGBoost_20260211_142120.pkl
│       ├── scaler_20260211_142120.pkl
│       ├── label_encoders_20260211_142120.pkl
│       ├── feature_columns_20260211_142120.json
│       └── ...other model files
└── src/
    └── predict_with_ensemble.py  # Prediction script
```

## What's Included

- **Trained Model**: Multi-target XGBoost model for predicting energy intensity and emissions
- **Preprocessing Objects**: Scaler, label encoders, and feature definitions
- **Prediction Script**: Core logic for making predictions
- **Template Data**: Sample input CSV for users to download

## What's NOT Included

To keep the Docker image small, the following have been excluded:
- Infrastructure/deployment code (in parent directory)
- Training notebooks and scripts
- Development documentation
- Test data and scripts
- Frontend files (deployed separately)

## Usage

The API automatically loads these models on startup. See the main API documentation for endpoints.
