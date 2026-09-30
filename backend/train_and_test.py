import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import time
import os

def main():
    print("Loading datasets...")
    start_time = time.time()
    
    # Paths relative to backend directory
    train_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'train.csv')
    test_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'test.csv')
    
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)

    features = ['no2', 'co', 'pm10', 'pm25']
    target = 'AQI(overall)'

    # Sample training data for fast, efficient performance without crashing memory
    SAMPLE_SIZE = min(100000, len(train_df))
    print(f"Sampling {SAMPLE_SIZE} records for rapid training out of {len(train_df)} total...")
    train_sampled = train_df.sample(n=SAMPLE_SIZE, random_state=42)

    X_train = train_sampled[features]
    y_train = train_sampled[target]

    X_test = test_df[features]
    y_test = test_df[target]

    print(f"Datasets loaded in {time.time() - start_time:.2f} seconds.")

    print(f"\nTraining Random Forest model (Using multiple CPU cores)...")
    # Using Random Forest to capture the non-linear nature of Air Quality Index calculations
    model = RandomForestRegressor(n_estimators=30, max_depth=15, n_jobs=-1, random_state=42)
    start_train = time.time()
    model.fit(X_train, y_train)
    print(f"Model successfully trained in {time.time() - start_train:.2f} seconds.")

    print("\nRunning inference on Test Data...")
    y_pred = model.predict(X_test)

    # Calculate metrics
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    print(f"\n=============================================")
    print(f"      MODEL PERFORMANCE ON TEST DATA         ")
    print(f"=============================================")
    print(f"Total Test Records Evaluated: {len(test_df)}")
    print(f"Mean Squared Error (MSE):     {mse:.4f}")
    print(f"R-Squared / Accuracy Score:   {r2:.4f} (1.00 is perfect)")
    print(f"=============================================\n")

    print("Sample Predictions vs Actual:")
    results = pd.DataFrame({'Actual AQI': y_test[:10].values, 'Predicted AQI': y_pred[:10].round(1)})
    print(results)

    # Save the strictly requested model file
    model_path = os.path.join(os.path.dirname(__file__), 'aqi_ml_model.pkl')
    joblib.dump(model, model_path)
    print(f"\n[SUCESS] Model saved and ready for integration at: {model_path}")

if __name__ == '__main__':
    main()
