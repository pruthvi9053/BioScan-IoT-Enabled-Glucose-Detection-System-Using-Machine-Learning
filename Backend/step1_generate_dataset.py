# ============================================================
# STEP 1 (FIXED) — Generate Better Synthetic Dataset
# ============================================================
# What changed from previous version?
#   The features now have stronger and more realistic
#   correlations with glucose. This gives the ML model
#   a proper signal to learn from.
#
#   In real life, these correlations come from actual
#   physics of light absorption in blood tissue.
#   For our prototype, we model them mathematically.
#
# Run this with:
#   python step1_generate_dataset.py
# ============================================================
 
import numpy as np
import pandas as pd
import os
 
np.random.seed(42)
 
print("=" * 55)
print("  STEP 1 (FIXED) — Generating Improved Dataset")
print("=" * 55)
 
N = 1200  # Slightly more samples for better training
print(f"\n  Generating {N} samples...")
 
# ── Generate glucose values ───────────────────────────────────
glucose = np.concatenate([
    np.random.normal(85,  12, int(N * 0.45)),   # Normal
    np.random.normal(113,  8, int(N * 0.25)),   # Pre-diabetic
    np.random.normal(170, 25, int(N * 0.20)),   # Diabetic
    np.random.normal(55,   7, int(N * 0.10)),   # Hypoglycaemic
])
np.random.shuffle(glucose)
glucose = np.clip(glucose, 40, 400)
 
records = []
 
for g in glucose:
 
    # ── Noise level for this sample ───────────────────────────
    noise = lambda val, pct: val * (1 + np.random.normal(0, pct))
 
    # ── Heart rate ────────────────────────────────────────────
    # High glucose → slightly higher HR (sympathetic nervous system)
    hr = 72 + (g - 100) * 0.08 + np.random.normal(0, 8)
    hr = np.clip(hr, 45, 130)
 
    # ── Perfusion Index ───────────────────────────────────────
    # High glucose → reduced peripheral blood flow → lower PI
    # This is the strongest real-world correlation we can model
    pi = 3.5 - (g - 70) * 0.012 + np.random.normal(0, 0.3)
    pi = np.clip(pi, 0.3, 7.0)
 
    # ── DC components ─────────────────────────────────────────
    # IR mean: glucose changes water/Hb absorption at 940nm
    ir_mean = 120000 + (g - 100) * 15 + np.random.normal(0, 3000)
    ir_mean = np.clip(ir_mean, 60000, 200000)
 
    # Red mean: glucose has stronger effect on 660nm absorption
    red_mean = 85000 + (g - 100) * 22 + np.random.normal(0, 2500)
    red_mean = np.clip(red_mean, 40000, 160000)
 
    # ── AC components (pulsatile) ─────────────────────────────
    ir_ac  = ir_mean  * (pi / 100.0) + np.random.normal(0, 50)
    red_ac = red_mean * (pi / 100.0) * 0.90 + np.random.normal(0, 40)
    ir_ac  = max(ir_ac, 100)
    red_ac = max(red_ac, 80)
 
    # ── Ratio R ───────────────────────────────────────────────
    # R = (AC_red/DC_red) / (AC_ir/DC_ir)
    # This ratio shifts with glucose due to differential absorption
    red_ratio = red_ac / red_mean
    ir_ratio  = ir_ac  / ir_mean
    ratio = (red_ratio / ir_ratio) if ir_ratio > 0 else 1.0
    # Add glucose-dependent shift + noise
    ratio = ratio + (g - 100) * 0.0004 + np.random.normal(0, 0.008)
    ratio = np.clip(ratio, 0.4, 1.6)
 
    # ── DC ratio ──────────────────────────────────────────────
    dc_ratio = red_mean / ir_mean
    dc_ratio = np.clip(dc_ratio + np.random.normal(0, 0.005), 0.4, 1.0)
 
    # ── Normalised IR ─────────────────────────────────────────
    ir_std   = max(ir_ac * 0.28 + np.random.normal(0, 30), 50)
    norm_ir  = ir_ac / ir_std
 
    # ── Signal quality ────────────────────────────────────────
    signal_quality = np.random.uniform(65, 100)
 
    records.append({
        'ir_mean':         round(noise(ir_mean,  0.01), 2),
        'ir_ac':           round(noise(ir_ac,    0.03), 2),
        'red_mean':        round(noise(red_mean, 0.01), 2),
        'red_ac':          round(noise(red_ac,   0.03), 2),
        'ratio':           round(ratio,    4),
        'dc_ratio':        round(dc_ratio, 4),
        'perfusion_index': round(noise(pi, 0.03), 4),
        'normalized_ir':   round(norm_ir,  4),
        'heart_rate':      round(hr, 1),
        'signal_quality':  round(signal_quality, 1),
        'glucose_mgdl':    round(g, 1),
    })
 
# ── Create DataFrame ──────────────────────────────────────────
df = pd.DataFrame(records)
 
def categorise(g):
    if g < 70:  return 'Low'
    if g < 100: return 'Normal'
    if g < 126: return 'Pre-Diabetic'
    if g < 200: return 'High'
    return 'Very High'
 
df['glucose_category'] = df['glucose_mgdl'].apply(categorise)
 
# ── Check correlations with glucose ───────────────────────────
print("\n  Feature correlations with glucose (higher = better signal):")
features = ['ir_mean','ir_ac','red_mean','red_ac','ratio',
            'dc_ratio','perfusion_index','normalized_ir','heart_rate']
corr = df[features].corrwith(df['glucose_mgdl']).abs().sort_values(ascending=False)
for feat, val in corr.items():
    bar = '█' * int(val * 20)
    print(f"    {feat:<20} {bar} {val:.3f}")
 
# ── Save CSV ──────────────────────────────────────────────────
os.makedirs('dataset', exist_ok=True)
csv_path = 'dataset/glucose_ppg_data.csv'
df.to_csv(csv_path, index=False)
 
print(f"\n  Saved {len(df)} rows → {csv_path}")
 
print(f"\n  Glucose distribution:")
print(df['glucose_category'].value_counts().to_string())
 
print(f"\n  Glucose stats (mg/dL):")
s = df['glucose_mgdl'].describe()
print(f"    Min  : {s['min']:.1f}  |  Max  : {s['max']:.1f}")
print(f"    Mean : {s['mean']:.1f}  |  Std  : {s['std']:.1f}")
 
print(f"\n{'=' * 55}")
print(f"  DONE! Better dataset ready.")
print(f"  Next → run: python step2_train_model.py")
print(f"{'=' * 55}")