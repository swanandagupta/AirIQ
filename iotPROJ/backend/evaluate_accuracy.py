import sqlite3
import pandas as pd
import joblib
import os
import sys
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import numpy as np

def evaluate():
    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, 'data', 'air_quality.db')
    model_path = os.path.join(base_dir, 'backend', 'aqi_ml_model.pkl')

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    # Load Model
    print("Loading ML model...")
    model = joblib.load(model_path)

    # Load Data from Database
    print("Fetching data from air_quality.db...")
    conn = sqlite3.connect(db_path)
    query = "SELECT mq135, mq137, aqi FROM readings"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if len(df) == 0:
        print("Error: No data found in the 'readings' table.")
        return

    print(f"Total records to evaluate: {len(df)}")

    # Prepare features for the ML model (matching aqi_engine.py logic)
    # The model expects: no2, co, pm10, pm25
    df['co'] = (df['mq135'] / 1023.0) * 60.0
    df['pm10'] = (df['mq135'] / 1023.0) * 300.0
    df['no2'] = (df['mq137'] / 1023.0) * 120.0
    df['pm25'] = (df['mq137'] / 1023.0) * 150.0

    features = ['no2', 'co', 'pm10', 'pm25']
    X = df[features]
    y_actual = df['aqi']

    # Predict
    print("Running inference...")
    y_pred = model.predict(X)

    # Calculate metrics
    mse = mean_squared_error(y_actual, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_actual, y_pred)
    r2 = r2_score(y_actual, y_pred)

    print("\n" + "="*45)
    print("      ACCURACY EVALUATION ON REAL DATA       ")
    print("="*45)
    print(f"Records Evaluated:    {len(df)}")
    print(f"Mean Absolute Error:  {mae:.4f}")
    print(f"Mean Squared Error:   {mse:.4f}")
    print(f"Root MSE:             {rmse:.4f}")
    print(f"R-Squared Score:      {r2:.4f}")
    print("="*45)

    # Comparison sample
    print("\nSample Comparisons (Last 10 records):")
    comparison = pd.DataFrame({
        'Stored AQI': y_actual.tail(10).values,
        'Predicted AQI': np.round(y_pred[-10:], 2),
        'Delta': np.round(np.abs(y_actual.tail(10).values - y_pred[-10:]), 2)
    })
    print(comparison)

    # Category Match Accuracy
    def get_category(aqi):
        if aqi <= 50: return 'Good'
        elif aqi <= 100: return 'Moderate'
        elif aqi <= 150: return 'Unhealthy for Sensitive'
        elif aqi <= 200: return 'Unhealthy'
        elif aqi <= 300: return 'Very Unhealthy'
        else: return 'Hazardous'

    actual_cats = [get_category(a) for a in y_actual]
    pred_cats = [get_category(p) for p in y_pred]
    matches = sum(1 for a, p in zip(actual_cats, pred_cats) if a == p)
    cat_accuracy = (matches / len(df)) * 100

    print(f"\nCategory Match Accuracy: {cat_accuracy:.2f}%")
    
    if cat_accuracy > 95:
        print("\n[CONCLUSION] The model is HIGHLY ACCURATE and consistent with stored data.")
    elif cat_accuracy > 80:
        print("\n[CONCLUSION] The model is MODERATELY ACCURATE but shows some deviations.")
    else:
        print("\n[CONCLUSION] Significant discrepancy detected. Model may need retraining or recalibration.")

if __name__ == "__main__":
    evaluate()
