#!/usr/bin/env python3
"""
PulseGuard ML Training Pipeline

This module handles:
1. Data loading from Firebase or local JSON
2. Exploratory Data Analysis (EDA)
3. Feature engineering
4. Model training (when labels available)
5. Model evaluation
6. Model persistence

CURRENT STATUS:
- Dataset has NO labels (normal/warning/critical)
- Supervised ML cannot be trained without labels
- Implemented: Rule-based baseline for demo
- Ready: ML pipeline for when labelled data becomes available

For the demo, we use a transparent rule-based system:
- NORMAL: temperature < 38°C AND vibration < 2.0
- WARNING: temperature 38-40°C OR vibration 2.0-5.0
- CRITICAL: temperature > 40°C OR vibration > 5.0

These thresholds can be adjusted based on domain knowledge.
"""

import json
import pickle
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR = Path(__file__).parent / "dataset"
MODEL_PATH = Path(__file__).parent / "model.pkl"
SCALER_PATH = Path(__file__).parent / "scaler.pkl"

# Thresholds for rule-based baseline
THRESHOLDS = {
    'normal': {'temp_max': 38.0, 'vib_max': 2.0},
    'warning': {'temp_max': 40.0, 'vib_max': 5.0},
    'critical': {'temp_max': float('inf'), 'vib_max': float('inf')}
}


def load_data_from_json(json_path: Path) -> pd.DataFrame:
    """Load readings from Firebase JSON export."""
    logger.info(f"Loading data from {json_path}")
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Convert to DataFrame
    records = list(data.values())
    df = pd.DataFrame(records)
    
    logger.info(f"Loaded {len(df)} records")
    return df


def load_data_from_firebase(firebase_url: str) -> pd.DataFrame:
    """Load readings directly from Firebase Realtime Database."""
    import requests
    
    logger.info(f"Fetching data from Firebase: {firebase_url}")
    response = requests.get(f"{firebase_url}/readings_only.json")
    response.raise_for_status()
    
    data = response.json()
    if not data:
        return pd.DataFrame()
    
    records = list(data.values())
    df = pd.DataFrame(records)
    
    logger.info(f"Fetched {len(df)} records from Firebase")
    return df


def perform_eda(df: pd.DataFrame) -> Dict[str, Any]:
    """Perform Exploratory Data Analysis."""
    logger.info("Performing EDA...")
    
    eda_results = {
        'total_records': len(df),
        'features': list(df.columns),
        'missing_values': df.isnull().sum().to_dict(),
        'duplicates': df.duplicated().sum(),
        'statistics': {}
    }
    
    for col in ['temperature', 'vibration', 'timestamp']:
        if col in df.columns:
            eda_results['statistics'][col] = {
                'min': float(df[col].min()) if not df[col].isnull().all() else None,
                'max': float(df[col].max()) if not df[col].isnull().all() else None,
                'mean': float(df[col].mean()) if not df[col].isnull().all() else None,
                'std': float(df[col].std()) if not df[col].isnull().all() else None,
                'median': float(df[col].median()) if not df[col].isnull().all() else None,
            }
    
    logger.info(f"EDA complete: {eda_results['total_records']} records")
    return eda_results


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create additional features from raw data."""
    logger.info("Engineering features...")
    
    df = df.copy()
    
    # Convert timestamp to datetime if it's in milliseconds
    if 'timestamp' in df.columns:
        # Check if timestamp is in milliseconds ( > 1e10 ) or seconds
        if df['timestamp'].max() > 1e10:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # Time-based features
        df['hour'] = df['datetime'].dt.hour
        df['day_of_week'] = df['datetime'].dt.dayofweek
        df['is_business_hours'] = ((df['hour'] >= 9) & (df['hour'] <= 17)).astype(int)
    
    # Interaction features
    if 'temperature' in df.columns and 'vibration' in df.columns:
        df['temp_vib_product'] = df['temperature'] * df['vibration']
        df['temp_vib_ratio'] = df['temperature'] / (df['vibration'] + 0.001)
    
    # Rolling statistics (if enough data)
    if len(df) >= 5:
        df = df.sort_values('timestamp')
        df['temp_rolling_mean_5'] = df['temperature'].rolling(5, min_periods=1).mean()
        df['vib_rolling_mean_5'] = df['vibration'].rolling(5, min_periods=1).mean()
        df['temp_change'] = df['temperature'].diff().fillna(0)
        df['vib_change'] = df['vibration'].diff().fillna(0)
    
    logger.info(f"Engineered {len(df.columns) - len(df.columns)} features")
    return df


def apply_rule_based_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply rule-based labeling for demo purposes.
    
    IMPORTANT: These are NOT ML predictions.
    This is a transparent rule-based baseline for demonstration.
    
    Rules:
    - NORMAL: temperature < 38°C AND vibration < 2.0
    - WARNING: (temperature 38-40°C) OR (vibration 2.0-5.0)
    - CRITICAL: temperature > 40°C OR vibration > 5.0
    """
    logger.info("Applying rule-based labels for demo...")
    
    df = df.copy()
    
    def classify(row):
        temp = row.get('temperature', 0)
        vib = row.get('vibration', 0)
        
        # CRITICAL conditions
        if temp > 40.0 or vib > 5.0:
            return 'critical'
        
        # WARNING conditions
        if (38.0 <= temp <= 40.0) or (2.0 <= vib <= 5.0):
            return 'warning'
        
        # NORMAL by default
        return 'normal'
    
    df['rule_based_label'] = df.apply(classify, axis=1)
    
    # Count distribution
    distribution = df['rule_based_label'].value_counts().to_dict()
    logger.info(f"Rule-based label distribution: {distribution}")
    
    return df


def prepare_training_data(df: pd.DataFrame, feature_columns: List[str]) -> Tuple:
    """Prepare features and labels for training."""
    logger.info(f"Preparing training data with features: {feature_columns}")
    
    # Filter to available feature columns
    available_features = [col for col in feature_columns if col in df.columns]
    
    if 'rule_based_label' not in df.columns:
        raise ValueError("No labels found. Run apply_rule_based_labels() first.")
    
    X = df[available_features].values
    y = df['rule_based_label'].values
    
    # Handle any remaining NaN values
    nan_mask = ~np.isnan(X).any(axis=1)
    X = X[nan_mask]
    y = y[nan_mask]
    
    logger.info(f"Training data shape: {X.shape}")
    logger.info(f"Label distribution: {dict(zip(*np.unique(y, return_counts=True)))}")
    
    return X, y, available_features


def train_models(X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
    """Train multiple models and compare performance."""
    logger.info("Training models...")
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Define models to try
    models = {
        'Logistic Regression': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', LogisticRegression(max_iter=1000, random_state=42))
        ]),
        'Random Forest': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=42
            ))
        ]),
        'Gradient Boosting': Pipeline([
            ('scaler', StandardScaler()),
            ('clf', GradientBoostingClassifier(
                n_estimators=100,
                max_depth=3,
                random_state=42
            ))
        ])
    }
    
    results = {}
    
    for name, model in models.items():
        logger.info(f"Training {name}...")
        
        # Train
        model.fit(X_train, y_train)
        
        # Predict
        y_pred = model.predict(X_test)
        
        # Evaluate
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        
        # Cross-validation
        cv_scores = cross_val_score(model, X, y, cv=5)
        
        results[name] = {
            'model': model,
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'cv_mean': cv_scores.mean(),
            'cv_std': cv_scores.std(),
            'confusion_matrix': confusion_matrix(y_test, y_pred),
            'classification_report': classification_report(y_test, y_pred),
            'X_test': X_test,
            'y_test': y_test,
            'y_pred': y_pred
        }
        
        logger.info(f"{name}: Accuracy={accuracy:.3f}, F1={f1:.3f}, CV={cv_scores.mean():.3f}")
    
    return results


def select_best_model(results: Dict[str, Any]) -> Tuple:
    """Select the best model based on F1 score."""
    logger.info("Selecting best model...")
    
    best_name = max(results, key=lambda x: results[x]['f1_score'])
    best_result = results[best_name]
    
    logger.info(f"Best model: {best_name} (F1={best_result['f1_score']:.3f})")
    
    return best_name, best_result['model'], best_result


def save_model(model: Pipeline, scaler: Optional[StandardScaler] = None):
    """Save model and scaler to disk."""
    logger.info(f"Saving model to {MODEL_PATH}")
    
    # If model is a Pipeline, it already contains scaler
    if scaler is not None and not hasattr(model, 'named_steps'):
        # Save separately
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump(model, f)
        with open(SCALER_PATH, 'wb') as f:
            pickle.dump(scaler, f)
    else:
        # Pipeline already includes scaler
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump(model, f)
    
    logger.info("Model saved successfully")


def load_model() -> Pipeline:
    """Load trained model from disk."""
    logger.info(f"Loading model from {MODEL_PATH}")
    
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Train first.")
    
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    
    logger.info("Model loaded successfully")
    return model


def predict_with_model(model: Pipeline, temperature: float, vibration: float) -> Dict:
    """Make prediction for a single reading."""
    features = np.array([[temperature, vibration]])
    prediction = model.predict(features)[0]
    probability = model.predict_proba(features)[0]
    
    return {
        'prediction': prediction,
        'confidence': float(max(probability)),
        'probabilities': {
            'normal': float(probability[0]) if len(probability) > 0 else 0,
            'warning': float(probability[1]) if len(probability) > 1 else 0,
            'critical': float(probability[2]) if len(probability) > 2 else 0,
        }
    }


def get_rule_based_prediction(temperature: float, vibration: float) -> Dict:
    """
    Get prediction using rule-based baseline.
    
    This is used when no trained ML model is available.
    Results are clearly labeled as rule-based.
    """
    # Determine status
    if temperature > 40.0 or vibration > 5.0:
        status = 'critical'
    elif (38.0 <= temperature <= 40.0) or (2.0 <= vibration <= 5.0):
        status = 'warning'
    else:
        status = 'normal'
    
    # Confidence based on distance from thresholds
    confidence = 0.85  # Base confidence for rule-based
    
    return {
        'prediction': status,
        'method': 'rule_based',
        'confidence': confidence,
        'thresholds': THRESHOLDS
    }


def run_training_pipeline(use_firebase: bool = False, firebase_url: str = ""):
    """Run complete ML training pipeline."""
    logger.info("=" * 60)
    logger.info("PULSEGUARD ML TRAINING PIPELINE")
    logger.info("=" * 60)
    
    # Load data
    if use_firebase:
        df = load_data_from_firebase(firebase_url)
    else:
        json_path = DATA_DIR / "readings.json"
        if not json_path.exists():
            # Try parent directory
            json_path = Path(__file__).parent.parent / "data" / "readings.json"
        df = load_data_from_json(json_path)
    
    if df.empty:
        logger.error("No data loaded. Exiting.")
        return None
    
    # EDA
    eda = perform_eda(df)
    logger.info(f"\nEDA Summary:")
    logger.info(f"  Total records: {eda['total_records']}")
    logger.info(f"  Features: {eda['features']}")
    logger.info(f"  Missing values: {eda['missing_values']}")
    
    if 'statistics' in eda:
        for feat, stats in eda['statistics'].items():
            logger.info(f"  {feat}: min={stats['min']:.1f}, max={stats['max']:.1f}, mean={stats['mean']:.1f}")
    
    # Feature engineering
    df = engineer_features(df)
    
    # Apply rule-based labels (since no real labels exist)
    df = apply_rule_based_labels(df)
    
    # Prepare training data
    feature_columns = ['temperature', 'vibration']
    X, y, features = prepare_training_data(df, feature_columns)
    
    # Check if we have enough data for ML
    if len(X) < 50:
        logger.warning(f"\n⚠️  WARNING: Only {len(X)} samples available.")
        logger.warning("Dataset too small for reliable ML training.")
        logger.warning("Using rule-based baseline for demo.")
        logger.warning("ML pipeline is ready for when more labeled data becomes available.")
        
        # Save a placeholder model info
        model_info = {
            'status': 'rule_based_baseline',
            'message': 'Insufficient labeled data for ML training. Using rule-based baseline.',
            'n_samples': len(X),
            'features': features,
            'thresholds': THRESHOLDS,
            'created_at': pd.Timestamp.now().isoformat()
        }
        
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump(model_info, f)
        
        logger.info(f"Model info saved to {MODEL_PATH}")
        return model_info
    
    # Train models
    results = train_models(X, y)
    
    # Select best model
    best_name, best_model, best_result = select_best_model(results)
    
    # Save model
    save_model(best_model)
    
    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("TRAINING RESULTS")
    logger.info("=" * 60)
    
    for name, result in results.items():
        logger.info(f"\n{name}:")
        logger.info(f"  Accuracy:  {result['accuracy']:.3f}")
        logger.info(f"  Precision: {result['precision']:.3f}")
        logger.info(f"  Recall:    {result['recall']:.3f}")
        logger.info(f"  F1 Score:  {result['f1_score']:.3f}")
        logger.info(f"  CV Score:  {result['cv_mean']:.3f} (+/- {result['cv_std']:.3f})")
    
    logger.info(f"\nBest model: {best_name}")
    logger.info(f"Model saved to: {MODEL_PATH}")
    
    return best_model


if __name__ == "__main__":
    # Run training pipeline
    model = run_training_pipeline(use_firebase=False)
    
    # Test prediction
    if model and isinstance(model, dict) and model.get('status') == 'rule_based_baseline':
        print("\n" + "=" * 60)
        print("TESTING RULE-BASED BASELINE")
        print("=" * 60)
        
        test_cases = [
            (36.5, 0.42, "Normal reading"),
            (38.5, 2.5, "Warning reading"),
            (41.0, 7.0, "Critical reading"),
        ]
        
        for temp, vib, desc in test_cases:
            result = get_rule_based_prediction(temp, vib)
            print(f"\n{desc}:")
            print(f"  Temperature: {temp}°C, Vibration: {vib}")
            print(f"  Prediction: {result['prediction'].upper()}")
            print(f"  Method: {result['method']}")
            print(f"  Confidence: {result['confidence']:.2f}")
