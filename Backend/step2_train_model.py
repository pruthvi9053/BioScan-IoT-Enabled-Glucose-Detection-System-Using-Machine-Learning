# ============================================================
# STEP 2 — Train the ML Model
# ============================================================
# What this script does:
#   Loads the dataset from Step 1, trains 4 different ML
#   models, compares their accuracy, picks the best one
#   and saves it to the models/ folder.
#
# What is ML training in simple words?
#   We show the model 800 examples (80% of 1000 samples)
#   with known glucose values. It learns the pattern.
#   Then we test it on 200 examples it has never seen.
#   The one with lowest error wins.
#
# Run this with:
#   python step2_train_model.py
# ============================================================
 
import numpy as np
import pandas as pd
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model    import Ridge
from sklearn.ensemble        import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm             import SVR
from sklearn.metrics         import mean_absolute_error, mean_squared_error, r2_score
 
print("=" * 55)
print("  STEP 2 — Training ML Models")
print("=" * 55)
 
# ── PART A: Load the dataset ──────────────────────────────────
print("\n  [1/5] Loading dataset...")
 
csv_path = 'dataset/glucose_ppg_data.csv'
 
if not os.path.exists(csv_path):
    print(f"\n  ERROR: File not found: {csv_path}")
    print("  Please run step1_generate_dataset.py first!")
    exit()
 
df = pd.read_csv(csv_path)
print(f"        Loaded {len(df)} rows, {len(df.columns)} columns")
 
# ── PART B: Separate features and target ──────────────────────
# Features (X) = what the sensor gives us (inputs)
# Target   (y) = glucose in mg/dL (what we want to predict)
 
print("\n  [2/5] Preparing features and target...")
 
FEATURES = [
    'ir_mean',
    'ir_ac',
    'red_mean',
    'red_ac',
    'ratio',
    'dc_ratio',
    'perfusion_index',
    'normalized_ir',
    'heart_rate',
    'signal_quality',
]
 
X = df[FEATURES].values   # 1000 rows × 10 columns (inputs)
y = df['glucose_mgdl'].values  # 1000 values (answers)
 
print(f"        Features shape : {X.shape}  (rows × columns)")
print(f"        Target shape   : {y.shape}  (glucose values)")
 
# ── PART C: Split into train and test ─────────────────────────
# 80% for training (model learns from these)
# 20% for testing  (model is tested on these — never seen before)
 
print("\n  [3/5] Splitting into train/test sets...")
 
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,       # 20% for testing
    random_state=42      # same split every run
)
 
print(f"        Training samples : {len(X_train)}")
print(f"        Testing samples  : {len(X_test)}")
 
# ── PART D: Scale the features ────────────────────────────────
# Why scale? Features have very different ranges:
#   ir_mean is ~120,000  but  ratio is ~0.9
# Scaling puts everything on the same scale (0 to 1 roughly)
# so no single feature dominates the model unfairly.
 
print("\n  [4/5] Scaling features...")
 
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)  # Learn scale from train
X_test_scaled  = scaler.transform(X_test)       # Apply same scale to test
 
print("        Done — all features normalised")
 
# ── PART E: Train and compare models ─────────────────────────
print("\n  [5/5] Training models and comparing...\n")
print(f"  {'Model':<25} {'MAE':>8} {'RMSE':>8} {'R²':>8}")
print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
 
# Define 4 models to compare
models = {
    'Ridge Regression':    Ridge(alpha=1.0),
    'Random Forest':       RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42),
    'Gradient Boosting':   GradientBoostingRegressor(n_estimators=100, learning_rate=0.1, random_state=42),
    'SVR':                 SVR(kernel='rbf', C=100, gamma='scale', epsilon=5),
}
 
results      = {}
best_name    = None
best_mae     = float('inf')
 
for name, model in models.items():
    # Train
    model.fit(X_train_scaled, y_train)
 
    # Predict on test set
    y_pred = model.predict(X_test_scaled)
 
    # Calculate error metrics
    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)
 
    results[name] = {
        'model': model,
        'mae':   mae,
        'rmse':  rmse,
        'r2':    r2,
        'y_pred': y_pred,
    }
 
    # Track best model
    marker = ''
    if mae < best_mae:
        best_mae  = mae
        best_name = name
        marker    = '  ← best so far'
 
    print(f"  {name:<25} {mae:>7.2f}  {rmse:>7.2f}  {r2:>7.4f}{marker}")
 
# ── Show winner ───────────────────────────────────────────────
print(f"\n  {'=' * 51}")
print(f"  WINNER: {best_name}")
print(f"  MAE  : {results[best_name]['mae']:.2f} mg/dL")
print(f"  RMSE : {results[best_name]['rmse']:.2f} mg/dL")
print(f"  R²   : {results[best_name]['r2']:.4f}")
print(f"  {'=' * 51}")
 
# ── Explain the metrics ───────────────────────────────────────
print("""
  What do these numbers mean?
  ───────────────────────────
  MAE  (Mean Absolute Error)
       Average error in mg/dL.
       Lower is better.
       Example: MAE=15 means predictions are off by ~15 mg/dL on average.
 
  RMSE (Root Mean Squared Error)
       Similar to MAE but punishes big errors more.
       Lower is better.
 
  R²   (R-squared / Accuracy score)
       How well the model explains glucose variation.
       1.0 = perfect | 0.0 = no better than guessing the mean
       Higher is better. Above 0.7 is good for this prototype.
""")
 
# ── Save best model and scaler ────────────────────────────────
os.makedirs('models', exist_ok=True)
 
best_model = results[best_name]['model']
joblib.dump(best_model, 'models/best_model.pkl')
joblib.dump(scaler,     'models/scaler.pkl')
 
# Save feature list so Flask server knows the order
import json
with open('models/features.json', 'w') as f:
    json.dump(FEATURES, f)
 
print("  Saved files:")
print("    models/best_model.pkl  ← trained model")
print("    models/scaler.pkl      ← feature scaler")
print("    models/features.json   ← feature names")
 
# ── Quick sample prediction test ─────────────────────────────
print("\n  Quick test — predicting 3 samples from test set:")
print(f"\n  {'Sample':<8} {'Actual':>10} {'Predicted':>12} {'Error':>10}")
print(f"  {'-'*44}")
 
for i in range(3):
    actual    = y_test[i]
    predicted = results[best_name]['y_pred'][i]
    error     = abs(actual - predicted)
    print(f"  {i+1:<8} {actual:>9.1f}  {predicted:>11.1f}  {error:>9.1f} mg/dL")
 
print(f"\n{'=' * 55}")
print(f"  DONE! Model trained and saved.")
print(f"  Next → run: python step3_evaluate.py")
print(f"{'=' * 55}")