"""
Prediction Script for Trained Ensemble Models

This script loads trained models and makes predictions on new data.
"""

import pandas as pd
import numpy as np
import pickle
import json
from pathlib import Path
from datetime import datetime
import argparse
import warnings
warnings.filterwarnings('ignore')


class EnsemblePredictor:
    """
    Load trained models and make predictions
    """
    
    def __init__(self, models_dir):
        """
        Initialize predictor with path to models directory
        
        Parameters:
        -----------
        models_dir : str
            Path to directory containing saved models
        """
        self.models_dir = Path(models_dir)
        self.model = None  # Single multi-target model
        self.scaler = None
        self.label_encoders = None
        self.feature_info = None
        
    def load_latest_models(self):
        """
        Load the most recently saved multi-target model and preprocessing objects
        """
        print("=" * 80)
        print("Loading trained multi-target model...")
        print("=" * 80)
        
        # Find latest model files
        models = sorted(self.models_dir.glob('best_model_multitarget_*.pkl'))
        scalers = sorted(self.models_dir.glob('scaler_*.pkl'))
        encoders = sorted(self.models_dir.glob('label_encoders_*.pkl'))
        features = sorted(self.models_dir.glob('feature_columns_*.json'))
        
        if not models:
            raise FileNotFoundError("No trained multi-target models found in the models directory")
        
        # Load latest versions
        with open(models[-1], 'rb') as f:
            self.model = pickle.load(f)
        print(f"Loaded multi-target model: {models[-1].name}")
        
        with open(scalers[-1], 'rb') as f:
            self.scaler = pickle.load(f)
        print(f"Loaded scaler: {scalers[-1].name}")
        
        with open(encoders[-1], 'rb') as f:
            self.label_encoders = pickle.load(f)
        print(f"Loaded label encoders: {encoders[-1].name}")
        
        with open(features[-1], 'r') as f:
            self.feature_info = json.load(f)
        print(f"Loaded feature info: {features[-1].name}")
        
        print("\nAll models and preprocessing objects loaded successfully!")
        
    def prepare_input_data(self, data):
        """
        Prepare input data for prediction
        
        Parameters:
        -----------
        data : pd.DataFrame
            Input data with same features as training data
            
        Returns:
        --------
        np.ndarray
            Scaled feature array ready for prediction
        """
        print("\n" + "=" * 80)
        print("Preparing input data...")
        print("=" * 80)
        
        # Ensure all required features are present
        feature_columns = self.feature_info['feature_columns']
        categorical_features = self.feature_info['categorical_features']
        numerical_features = self.feature_info['numerical_features']
        
        missing_features = [col for col in feature_columns if col not in data.columns]
        if missing_features:
            raise ValueError(f"Missing required features: {missing_features}")
        
        # Create a copy with only needed features
        X = data[feature_columns].copy()
        
        # Encode categorical features
        for col in categorical_features:
            if col in self.label_encoders:
                le = self.label_encoders[col]
                # Handle unknown categories by mapping to most common class (first class)
                X[col] = X[col].fillna(le.classes_[0])
                X[col] = X[col].apply(lambda x: le.transform([str(x)])[0] 
                                      if str(x) in le.classes_ 
                                      else le.transform([le.classes_[0]])[0])
        
        # Fill missing numerical values with median (or 0)
        for col in numerical_features:
            X[col] = X[col].fillna(0)
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        print(f"Prepared {len(X)} samples for prediction")
        
        return X_scaled
    
    def predict(self, data):
        """
        Make predictions using trained models
        
        Parameters:
        -----------
        data : pd.DataFrame
            Input data
            
        Returns:
        --------
        pd.DataFrame
            Input data with predictions added
        """
        print("\n" + "=" * 80)
        print("Making predictions...")
        print("=" * 80)
        
        # Prepare data
        X_scaled = self.prepare_input_data(data)
        
        # Make predictions (multi-target model returns both predictions)
        predictions = self.model.predict(X_scaled)
        
        # Extract individual target predictions
        # predictions shape: (n_samples, 2) where [:, 0] is energy and [:, 1] is emissions
        energy_predictions = predictions[:, 0]
        emissions_predictions = predictions[:, 1]
        
        # Add predictions to dataframe with units
        result_df = data.copy()
        result_df['predicted_energy_intensity_kwh_per_sqft'] = energy_predictions
        result_df['predicted_co2_emissions_co2e_kg'] = emissions_predictions
        
        print(f"\nPrediction Summary:")
        print(f"  Energy Intensity (kWh/sqft) - Mean: {energy_predictions.mean():.2f}, "
              f"Std: {energy_predictions.std():.2f}, "
              f"Range: [{energy_predictions.min():.2f}, {energy_predictions.max():.2f}]")
        print(f"  CO2 Emissions (CO2e kg) - Mean: {emissions_predictions.mean():.2f}, "
              f"Std: {emissions_predictions.std():.2f}, "
              f"Range: [{emissions_predictions.min():.2f}, {emissions_predictions.max():.2f}]")
        
        return result_df
    
    def predict_from_file(self, input_file, output_file=None):
        """
        Load data from file, make predictions, and save results
        
        Parameters:
        -----------
        input_file : str
            Path to input CSV or Excel file
        output_file : str, optional
            Path to save predictions. If None, auto-generates filename
        """
        print("\n" + "=" * 80)
        print("Predicting from file...")
        print("=" * 80)
        
        # Load data (support both CSV and Excel)
        print(f"\nLoading data from: {input_file}")
        file_path = Path(input_file)
        if file_path.suffix.lower() in ['.xlsx', '.xls']:
            data = pd.read_excel(input_file)
        else:
            data = pd.read_csv(input_file)
        print(f"Loaded {len(data)} rows, {len(data.columns)} columns")
        
        # Make predictions
        predictions_df = self.predict(data)
        
        # Save results
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_name = Path(input_file).stem
            output_file = self.models_dir.parent / f"predictions_{input_name}_{timestamp}.csv"
        
        predictions_df.to_csv(output_file, index=False)
        print(f"\nPredictions saved to: {output_file}")
        print(f"Predicted {len(predictions_df)} samples successfully!")
        
        return predictions_df


def main():
    """
    Command-line interface for making predictions
    """
    parser = argparse.ArgumentParser(description='Make predictions using trained ensemble models')
    parser.add_argument('input_file', type=str, help='Path to input CSV file')
    parser.add_argument('--models-dir', type=str, default=None,
                       help='Path to models directory (default: output/models)')
    parser.add_argument('--output', type=str, default=None,
                       help='Path to save predictions (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Set default models directory
    if args.models_dir is None:
        base_dir = Path(__file__).parent.parent
        models_dir = base_dir / "output" / "models"
    else:
        models_dir = Path(args.models_dir)
    
    # Create predictor and make predictions
    predictor = EnsemblePredictor(models_dir)
    predictor.load_latest_models()
    predictor.predict_from_file(args.input_file, args.output)


if __name__ == "__main__":
    # If no command-line arguments, run with default paths
    import sys
    if len(sys.argv) == 1:
        print("Usage: python predict_with_ensemble.py <input_file> [--models-dir <dir>] [--output <file>]")
        print("\nExamples:")
        print("  python predict_with_ensemble.py data/input_data.xlsx")
        print("  python predict_with_ensemble.py output/canadianized_comstock_buildings.csv")
        print("  python predict_with_ensemble.py data/input_data.xlsx --output output/my_predictions.csv")
    else:
        main()
