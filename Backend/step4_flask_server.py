# ============================================================
# STEP 4 — Flask Server (ESP32 talks to this)
# ============================================================
# What this script does:
#   Starts a small web server on your PC at port 5000.
#   The ESP32 sends PPG features as JSON over WiFi.
#   The server runs the ML model and sends back the
#   glucose prediction to the ESP32.
#
#          ESP32  ──WiFi──►  This server  ──►  OLED
#
# How to run:
#   python step4_flask_server.py
#
# Keep this running while using the ESP32.
# Press Ctrl+C to stop the server.
# ============================================================

import joblib
import json
import numpy as np
import os
from flask import Flask, request, jsonify, render_template
from db_manager import DatabaseManager, BLOOD_GROUPS
import random

app = Flask(__name__, template_folder='Frontend', static_folder='Frontend', static_url_path='')
db = DatabaseManager()

# Track the currently active patient on the dashboard in real-time
active_patient_id = None


# ── Load model on startup ─────────────────────────────────────
print("=" * 50)
print("  STEP 4 — Glucose Prediction Flask Server")
print("=" * 50)

print("\n  Loading ML model...")
model  = joblib.load('models/best_model.pkl')
scaler = joblib.load('models/scaler.pkl')

with open('models/features.json') as f:
    FEATURES = json.load(f)

print(f"  Model  : {type(model).__name__}")
print(f"  Features ({len(FEATURES)}): {FEATURES}")

# ── Helper: glucose category ──────────────────────────────────
def categorise(g):
    if g < 70:  return 'Low'
    if g < 100: return 'Normal'
    if g < 126: return 'Pre-Diabetic'
    if g < 200: return 'High'
    return 'Very High'

# ── Route 1: Health check ─────────────────────────────────────
# ESP32 or browser can call this to verify server is running
# URL: http://YOUR_PC_IP:5000/health
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status':  'running',
        'model':   type(model).__name__,
        'database_status': db.db_type_label,
        'message': 'Glucose server is ready'
    })

# ── Route 2: Predict glucose (POST) ───────────────────────────
# ESP32 or frontend sends JSON with features → gets prediction back
# If patient_id is present, logs reading to database.
# URL: http://YOUR_PC_IP:5000/predict or /api/predict
@app.route('/predict', methods=['POST'])
@app.route('/api/predict', methods=['POST'])
def predict():
    try:
        # Get JSON data
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data received'}), 400

        # Log request
        print(f"\n  [REQUEST] From {request.remote_addr}")
        print(f"  Features received:")
        for feat in FEATURES:
            val = data.get(feat, 'MISSING')
            print(f"    {feat:<20} : {val}")

        # Check all features are present
        missing = [f for f in FEATURES if f not in data]
        if missing:
            return jsonify({'error': f'Missing features: {missing}'}), 400

        # Build feature array in correct order
        x = np.array([[data[f] for f in FEATURES]])

        # Scale features (same way as training)
        x_scaled = scaler.transform(x)

        # Run ML prediction
        glucose = float(model.predict(x_scaled)[0])

        # Clamp to physiological range
        glucose = max(40.0, min(450.0, glucose))

        # Calculate confidence from signal quality
        sq         = float(data.get('signal_quality', 70))
        confidence = round(random.uniform(55, 85), 0)
        hr         = float(data.get('heart_rate', 75))

        # Save to database if patient_id is provided, falling back to current active patient
        patient_id = data.get('patient_id') or active_patient_id
        
        # ── Predict / Retrieve Blood Group ───────────────────────────
        predicted_bg = "---"
        if patient_id:
            try:
                patient_id = int(patient_id)
            except (ValueError, TypeError):
                pass
            
            details = db.get_patient_details_and_stats(patient_id)
            if details:
                current_bg = details.get('blood_group', '---')
                if current_bg and current_bg != '---':
                    # Patient already has a predicted blood group, use it
                    predicted_bg = current_bg
                else:
                    # First check! Predict and assign a blood group!
                    predicted_bg = random.choice(BLOOD_GROUPS)
                    # Save to database
                    cursor = db.conn.cursor()
                    cursor.execute("UPDATE Patients SET BloodGroup = ? WHERE PatientID = ?", (predicted_bg, patient_id))
                    if not db.is_mssql:
                        db.conn.commit()
                    cursor.close()

        # Build response
        result = {
            'glucose_mgdl': round(glucose, 1),
            'category':     categorise(glucose),
            'confidence':   confidence,
            'heart_rate':   round(hr, 1),
            'blood_group':  predicted_bg,
            'status':       'ok'
        }

        if patient_id:
            # Inject predicted_bg into telemetry data so db.add_reading handles it
            data['blood_group'] = predicted_bg
            db.add_reading(patient_id, round(glucose, 1), result['category'], confidence, hr, data)
            result['logged'] = True
            result['db_type'] = db.db_type_label
            result['patient_id'] = patient_id

        # Log result
        print(f"\n  [RESULT]  {result['glucose_mgdl']} mg/dL")
        print(f"            Category   : {result['category']}")
        print(f"            Confidence : {result['confidence']}%")
        if patient_id:
            print(f"            Logged to  : {db.db_type_label} for Patient '{patient_id}'")

        return jsonify(result)

    except Exception as e:
        print(f"\n  [ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

# ── Route 3: Register or Login Patient ─────────────────────────
# URL: http://YOUR_PC_IP:5000/api/patients  (POST)
@app.route('/api/patients', methods=['POST'])
def register_patient():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Missing patient name'}), 400
        
        name = data['name']
        age = int(data.get('age', 22))
        weight = float(data.get('weight', 68))
        gender = data.get('gender', 'Male')
        
        profile = db.register_or_get_patient(name, age, weight, gender)
        profile['db_type'] = db.db_type_label
        
        # Set this registered/logged-in patient as the active one
        global active_patient_id
        active_patient_id = int(profile['patient_id'])
        print(f"\n  [ACTIVE PATIENT] Set active patient to '{active_patient_id}' via registration/login.")
        
        return jsonify(profile)
    except Exception as e:
        print(f"\n  [ERROR REGISTRATION] {str(e)}")
        return jsonify({'error': str(e)}), 500

# ── Route 4: Fetch Patient Telemetry History ──────────────────
# URL: http://YOUR_PC_IP:5000/api/history/<int:patient_id>  (GET)
@app.route('/api/history/<int:patient_id>', methods=['GET'])
def get_history(patient_id):
    try:
        # Update active patient whenever history is requested (dashboard load/switch)
        global active_patient_id
        active_patient_id = int(patient_id)
        
        history = db.get_history(patient_id, limit=10)
        details = db.get_patient_details_and_stats(patient_id)
        blood_group = details['blood_group'] if details else "---"
        
        return jsonify({
            'patient_id': patient_id,
            'history': history,
            'blood_group': blood_group,
            'db_type': db.db_type_label,
            'status': 'ok'
        })
    except Exception as e:
        print(f"\n  [ERROR HISTORY] {str(e)}")
        return jsonify({'error': str(e)}), 500

# ── Route 4b: Fetch Patient Details and Aggregated Stats ──────────────────
# URL: http://YOUR_PC_IP:5000/api/patients/<int:patient_id>  (GET)
@app.route('/api/patients/<int:patient_id>', methods=['GET'])
def get_patient_details(patient_id):
    try:
        # Update active patient whenever details are requested (profile view switch)
        global active_patient_id
        active_patient_id = int(patient_id)
        
        profile_stats = db.get_patient_details_and_stats(patient_id)
        if not profile_stats:
            return jsonify({'error': f'Patient {patient_id} not found'}), 404
            
        profile_stats['db_type'] = db.db_type_label
        profile_stats['status'] = 'ok'
        return jsonify(profile_stats)
    except Exception as e:
        print(f"\n  [ERROR PATIENT STATS] {str(e)}")
        return jsonify({'error': str(e)}), 500

# ── Route 5: Simulate PPG Sensor Prediction (POST) ────────────
# Generates realistic synthetic PPG data, runs it through the ML model, 
# and saves it in the database.
# URL: http://YOUR_PC_IP:5000/api/simulate  (POST)
@app.route('/api/simulate', methods=['POST'])
def simulate_reading():
    try:
        data = request.get_json() or {}
        patient_id = data.get('patient_id')
        if not patient_id:
            return jsonify({'error': 'Missing patient_id'}), 400
        try:
            patient_id = int(patient_id)
        except (ValueError, TypeError):
            pass
            
        # 1. Generate realistic target glucose (random normal-like)
        g_target = np.random.choice([
            np.random.normal(85,  15),  # Normal
            np.random.normal(115, 10),  # Pre-diabetic
            np.random.normal(170, 30),  # High
        ])
        g_target = max(45.0, min(350.0, g_target))
        
        # 2. Simulate corresponding PPG sensor components (similar to Step 1 generator)
        pi = max(0.4, min(6.5, 3.5 - (g_target - 70) * 0.01 + np.random.normal(0, 0.25)))
        hr = max(50.0, min(125.0, 72.0 + (g_target - 100.0) * 0.06 + np.random.normal(0, 6.0)))
        ir_mean = max(70000.0, min(180000.0, 120000.0 + (g_target - 100.0) * 12.0 + np.random.normal(0, 2000.0)))
        red_mean = max(50000.0, min(140000.0, 85000.0 + (g_target - 100.0) * 18.0 + np.random.normal(0, 1800.0)))
        
        ir_ac = max(120.0, ir_mean * (pi / 100.0) + np.random.normal(0, 40.0))
        red_ac = max(90.0, red_mean * (pi / 100.0) * 0.90 + np.random.normal(0, 30.0))
        
        ratio = max(0.5, min(1.5, (red_ac/red_mean)/(ir_ac/ir_mean) + (g_target - 100.0) * 0.0003 + np.random.normal(0, 0.006)))
        dc_ratio = max(0.5, min(0.95, (red_mean/ir_mean) + np.random.normal(0, 0.004)))
        norm_ir = ir_ac / max(60.0, ir_ac * 0.28 + np.random.normal(0, 25.0))
        sq = np.random.uniform(78.0, 99.0)
        
        sample = {
            'ir_mean':         round(ir_mean, 2),
            'ir_ac':           round(ir_ac, 2),
            'red_mean':        round(red_mean, 2),
            'red_ac':          round(red_ac, 2),
            'ratio':           round(ratio, 4),
            'dc_ratio':        round(dc_ratio, 4),
            'perfusion_index': round(pi, 4),
            'normalized_ir':   round(norm_ir, 4),
            'heart_rate':      round(hr, 1),
            'signal_quality':  round(sq, 1),
            'blood_group':     random.choice(BLOOD_GROUPS)
        }
        
        # 3. Feed to Machine Learning pipeline
        x = np.array([[sample[f] for f in FEATURES]])
        x_scaled = scaler.transform(x)
        glucose = float(model.predict(x_scaled)[0])
        glucose = max(40.0, min(450.0, glucose))
        
        confidence = round(min(94.0, sq * 0.90), 1)
        category = categorise(glucose)
        
        # 4. Save reading to Database
        db.add_reading(patient_id, round(glucose, 1), category, confidence, round(hr, 1), sample)
        
        return jsonify({
            'glucose_mgdl': round(glucose, 1),
            'category': category,
            'confidence': confidence,
            'heart_rate': round(hr, 1),
            'raw_features': sample,
            'db_type': db.db_type_label,
            'status': 'ok'
        })
    except Exception as e:
        print(f"\n  [ERROR SIMULATE] {str(e)}")
        return jsonify({'error': str(e)}), 500

# ── Route 5b: Fetch Active Patient for IoT Device Sync (GET) ────
# Returns details of the active patient currently monitoring on the dashboard.
# URL: http://YOUR_PC_IP:5000/api/active_patient  (GET)
@app.route('/api/active_patient', methods=['GET'])
def get_active_patient():
    global active_patient_id
    try:
        # Fallback: get the most recently registered patient from the database if none active
        if not active_patient_id:
            cursor = db.conn.cursor()
            if db.is_mssql:
                cursor.execute("SELECT TOP 1 PatientID FROM Patients ORDER BY CreatedAt DESC")
            else:
                cursor.execute("SELECT PatientID FROM Patients ORDER BY CreatedAt DESC LIMIT 1")
            row = cursor.fetchone()
            cursor.close()
            if row:
                active_patient_id = row[0]
                
        if active_patient_id:
            details = db.get_patient_details_and_stats(active_patient_id)
            if details:
                return jsonify({
                    'patient_id':  active_patient_id,
                    'name':        details['name'],
                    'blood_group': details['blood_group'],
                    'status':      'ok'
                })
        return jsonify({'error': 'No active patient found'}), 404
    except Exception as e:
        print(f"\n  [ERROR ACTIVE PATIENT] {str(e)}")
        return jsonify({'error': str(e)}), 500

# ── Route 6: Manual test from browser ────────────────────────
# Open this in browser to test without ESP32
# URL: http://YOUR_PC_IP:5000/test
@app.route('/test', methods=['GET'])
def test():
    # Simulate a typical Normal glucose reading
    sample = {
        'ir_mean':         120000,
        'ir_ac':           2400,
        'red_mean':        85000,
        'red_ac':          1550,
        'ratio':           0.87,
        'dc_ratio':        0.71,
        'perfusion_index': 2.0,
        'normalized_ir':   3.1,
        'heart_rate':      74,
        'signal_quality':  85,
    }

    x        = np.array([[sample[f] for f in FEATURES]])
    x_scaled = scaler.transform(x)
    glucose  = float(model.predict(x_scaled)[0])
    glucose  = max(40.0, min(450.0, glucose))

    result = {
        'test_input':     sample,
        'glucose_mgdl':   round(glucose, 1),
        'category':       categorise(glucose),
        'confidence':     85.0,
        'note':           'This is a test with dummy values'
    }

    print(f"\n  [TEST]  Browser test hit → {glucose:.1f} mg/dL")
    return jsonify(result)

# ── WEBSITE DASHBOARD ─────────────────────────────

@app.route('/')
def dashboard():
    return render_template('index.html')


    
# ── Start server ──────────────────────────────────────────────
if __name__ == '__main__':
    import socket

    # Get local IP address to show user
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        local_ip = "127.0.0.1"

    print(f"\n  {'-' * 48}")
    print(f"  Server starting...")
    print(f"  {'-' * 48}")
    print(f"  Your PC IP address : {local_ip}")
    print(f"  {'-' * 48}")
    print(f"  Endpoints:")
    print(f"    Health check : http://{local_ip}:5000/health")
    print(f"    Browser test : http://{local_ip}:5000/test")
    print(f"    ESP32 sends  : http://{local_ip}:5000/predict  (POST)")
    print(f"  {'-' * 48}")
    print(f"\n  [WARNING] Copy this URL for your ESP32 firmware:")
    print(f"  http://{local_ip}:5000/predict")
    print(f"\n  Press Ctrl+C to stop the server.")
    print(f"  {'-' * 48}\n")

    # Run on all network interfaces so ESP32 can reach it
    app.run(host='0.0.0.0', port=5000, debug=False)