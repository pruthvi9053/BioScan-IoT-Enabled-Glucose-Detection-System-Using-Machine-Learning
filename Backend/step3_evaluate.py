# ============================================================
# STEP 3 — Evaluate the Trained Model
# ============================================================
# What this script does:
#   Loads the saved model and tests it thoroughly.
#   Shows accuracy per glucose category, error distribution,
#   and how many predictions fall within safe error ranges.
#
# Run this with:
#   python step3_evaluate.py
# ============================================================

import numpy as np
import pandas as pd
import joblib
import json
import os

print("=" * 55)
print("  STEP 3 — Model Evaluation")
print("=" * 55)

# ── Load model, scaler and features ──────────────────────────
print("\n  [1/4] Loading saved model...")

if not os.path.exists('models/best_model.pkl'):
    print("  ERROR: No model found! Run step2_train_model.py first.")
    exit()

model   = joblib.load('models/best_model.pkl')
scaler  = joblib.load('models/scaler.pkl')

with open('models/features.json') as f:
    FEATURES = json.load(f)

print(f"        Model loaded: {type(model).__name__}")
print(f"        Features    : {FEATURES}")

# ── Load full dataset ─────────────────────────────────────────
print("\n  [2/4] Loading dataset...")
df = pd.read_csv('dataset/glucose_ppg_data.csv')

from sklearn.model_selection import train_test_split
X = df[FEATURES].values
y = df['glucose_mgdl'].values

_, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
X_test_scaled = scaler.transform(X_test)

print(f"        Test samples: {len(X_test)}")

# ── Run predictions ───────────────────────────────────────────
print("\n  [3/4] Running predictions on test set...")
y_pred = model.predict(X_test_scaled)
errors = np.abs(y_pred - y_test)

# ── Overall metrics ───────────────────────────────────────────
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

mae  = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
r2   = r2_score(y_test, y_pred)

print(f"\n  [4/4] Results:\n")
print(f"  {'─' * 45}")
print(f"  Overall Performance")
print(f"  {'─' * 45}")
print(f"  MAE  (avg error)    : {mae:.2f} mg/dL")
print(f"  RMSE                : {rmse:.2f} mg/dL")
print(f"  R²                  : {r2:.4f}")

# ── Clinical accuracy thresholds ─────────────────────────────
within_10  = np.mean(errors <= 10)  * 100
within_15  = np.mean(errors <= 15)  * 100
within_20  = np.mean(errors <= 20)  * 100
within_20p = np.mean(errors / y_test <= 0.20) * 100

print(f"\n  {'─' * 45}")
print(f"  Prediction Accuracy Thresholds")
print(f"  {'─' * 45}")
print(f"  Within ±10 mg/dL  : {within_10:.1f}%")
print(f"  Within ±15 mg/dL  : {within_15:.1f}%")
print(f"  Within ±20 mg/dL  : {within_20:.1f}%")
print(f"  Within ±20%       : {within_20p:.1f}%")
print(f"  (ISO 15197 standard needs 95% within ±15 mg/dL — for reference only)")

# ── Category-wise accuracy ────────────────────────────────────
def categorise(g):
    if g < 70:  return 'Low'
    if g < 100: return 'Normal'
    if g < 126: return 'Pre-Diabetic'
    if g < 200: return 'High'
    return 'Very High'

categories   = [categorise(g) for g in y_test]
cat_unique   = ['Low', 'Normal', 'Pre-Diabetic', 'High', 'Very High']

print(f"\n  {'─' * 45}")
print(f"  Accuracy by Glucose Category")
print(f"  {'─' * 45}")
print(f"  {'Category':<15} {'Samples':>8} {'Avg Error':>12} {'Within ±15':>12}")

for cat in cat_unique:
    idx = [i for i, c in enumerate(categories) if c == cat]
    if len(idx) == 0:
        continue
    cat_errors = errors[idx]
    avg_err    = cat_errors.mean()
    within15   = np.mean(cat_errors <= 15) * 100
    print(f"  {cat:<15} {len(idx):>8} {avg_err:>10.2f}   {within15:>9.1f}%")

# ── Category prediction match ─────────────────────────────────
pred_categories   = [categorise(p) for p in y_pred]
correct_cat       = sum(a == p for a, p in zip(categories, pred_categories))
cat_accuracy      = correct_cat / len(categories) * 100

print(f"\n  {'─' * 45}")
print(f"  Category Classification")
print(f"  {'─' * 45}")
print(f"  Correct category predicted: {correct_cat}/{len(categories)} = {cat_accuracy:.1f}%")
print(f"  (e.g. actual=High, predicted=High → correct)")

# ── Sample predictions table ──────────────────────────────────
print(f"\n  {'─' * 45}")
print(f"  Sample Predictions (first 10 from test set)")
print(f"  {'─' * 45}")
print(f"  {'#':<4} {'Actual':>8} {'Predicted':>11} {'Error':>8} {'Category':>14} {'Match':>6}")
print(f"  {'─' * 55}")

for i in range(min(10, len(y_test))):
    actual    = y_test[i]
    predicted = y_pred[i]
    error     = abs(actual - predicted)
    cat_a     = categorise(actual)
    cat_p     = categorise(predicted)
    match     = "✓" if cat_a == cat_p else "✗"
    print(f"  {i+1:<4} {actual:>8.1f} {predicted:>11.1f} {error:>7.1f}   {cat_a:>13}  {match:>5}")

# ── Simple error histogram ────────────────────────────────────
print(f"\n  {'─' * 45}")
print(f"  Error Distribution (text histogram)")
print(f"  {'─' * 45}")

bins   = [0, 5, 10, 15, 20, 30, 50, 100]
labels = ['0–5', '5–10', '10–15', '15–20', '20–30', '30–50', '>50']

for i in range(len(labels)):
    lo  = bins[i]
    hi  = bins[i + 1]
    cnt = np.sum((errors >= lo) & (errors < hi))
    pct = cnt / len(errors) * 100
    bar = '█' * int(pct / 2)
    print(f"  {labels[i]:<8} mg/dL | {bar:<25} {cnt:>4} samples ({pct:.1f}%)")

# ── Final verdict ─────────────────────────────────────────────
print(f"\n  {'═' * 45}")
print(f"  VERDICT")
print(f"  {'═' * 45}")

if r2 >= 0.75:
    print(f"  ✅ R² = {r2:.4f} — Model is working well for a prototype")
elif r2 >= 0.50:
    print(f"  ⚠️  R² = {r2:.4f} — Moderate accuracy, acceptable for prototype")
else:
    print(f"  ❌ R² = {r2:.4f} — Model needs improvement")

if mae <= 20:
    print(f"  ✅ MAE = {mae:.2f} mg/dL — Good average accuracy")
else:
    print(f"  ⚠️  MAE = {mae:.2f} mg/dL — Moderate error, prototype acceptable")

print(f"\n  ⚠️  REMINDER: This is a RESEARCH PROTOTYPE.")
print(f"  Not for medical use. Real accuracy will be")
print(f"  lower until calibrated with actual PPG data.")

print(f"\n{'=' * 55}")
print(f"  DONE! Evaluation complete.")
print(f"  Next → run: python step4_flask_server.py")
print(f"{'=' * 55}")