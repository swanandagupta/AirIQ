import sqlite3
import pandas as pd
import joblib
import os
import json
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import numpy as np

def evaluate():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, 'data', 'air_quality.db')
    model_path = os.path.join(base_dir, 'backend', 'aqi_ml_model.pkl')

    if not os.path.exists(db_path) or not os.path.exists(model_path):
        return

    model = joblib.load(model_path)
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT mq135, mq137, aqi FROM readings", conn)
    conn.close()

    if len(df) == 0:
        return

    df['co'] = (df['mq135'] / 1023.0) * 60.0
    df['pm10'] = (df['mq135'] / 1023.0) * 300.0
    df['no2'] = (df['mq137'] / 1023.0) * 120.0
    df['pm25'] = (df['mq137'] / 1023.0) * 150.0

    features = ['no2', 'co', 'pm10', 'pm25']
    y_actual = df['aqi']
    y_pred = model.predict(df[features])

    mse = mean_squared_error(y_actual, y_pred)
    r2 = r2_score(y_actual, y_pred)
    mae = mean_absolute_error(y_actual, y_pred)

    results = {
        'count': int(len(df)),
        'mse': float(mse),
        'rmse': float(np.sqrt(mse)),
        'mae': float(mae),
        'r2': float(r2),
        'samples': []
    }

    # Add samples
    for i in range(min(5, len(df))):
        results['samples'].append({
            'mq135': float(df['mq135'].iloc[i]),
            'mq137': float(df['mq137'].iloc[i]),
            'stored': float(y_actual.iloc[i]),
            'predicted': float(y_pred[i])
        })

    with open('evaluation_results.json', 'w') as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    evaluate()
