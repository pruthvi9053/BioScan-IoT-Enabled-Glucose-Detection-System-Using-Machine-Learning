# BioScan: IoT-Enabled Glucose Detection System Using Machine Learning

### Optical PPG-Based Glucose Estimation Using ESP32, MAX30102, and Gradient Boosting Machine Learning

---

## Project Overview

BioScan is an IoT-enabled healthcare monitoring system that performs non-invasive glucose estimation using optical PPG (Photoplethysmography) signals captured from a fingertip. The system uses a MAX30102 sensor connected to an ESP32 microcontroller to collect Red and Infrared light signals, extract physiological features, and predict glucose levels using a trained Machine Learning model.

The project also includes a Flask backend server, SQL Server database integration, and a real-time web dashboard for patient registration, monitoring, and historical record management.

> **Note:** Blood Group prediction is included only as a research prototype feature and should not be considered a validated medical prediction system.

---

## Key Features

- Non-invasive glucose estimation
- Real-time PPG signal acquisition
- ESP32 and MAX30102 integration
- Machine Learning-based glucose prediction
- Flask REST API backend
- SQL Server database integration
- Patient registration system
- Smart healthcare dashboard
- Live monitoring and historical records
- OLED display output
- Signal quality assessment
- Heart rate estimation

---

## Hardware Components

| Component | Quantity | Approx Price (INR) | Purpose |
|------------|------------|------------|------------|
| ESP32 WROOM-32 | 1 | ₹350 | Main Microcontroller |
| MAX30102 PPG Sensor | 1 | ₹180 | Red & IR Signal Acquisition |
| SSD1306 OLED Display (0.96") | 1 | ₹120 | Result Display |
| Breadboard | 1 | ₹60 | Circuit Prototyping |
| Jumper Wires | 1 Set | ₹50 | Connections |
| 18650 Battery (2500mAh) | 1 | ₹200 | Portable Power Supply |
| Battery Holder | 1 | ₹50 | Battery Mounting |
| USB Cable | 1 | ₹100 | Programming & Power |

### Total Approximate Cost

```text
₹1,100 – ₹1,300
```

---

## Hardware Connections

### MAX30102

| MAX30102 | ESP32 |
|-----------|-----------|
| VIN | 3.3V |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

### OLED Display

| OLED | ESP32 |
|---------|---------|
| VCC | 3.3V |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |

Both OLED and MAX30102 share the same I2C bus.

---

## Software Stack

### Embedded

- Arduino IDE
- ESP32 Board Package
- Adafruit SSD1306
- Adafruit GFX
- SparkFun MAX3010x
- ArduinoJson
- WiFi
- HTTPClient

### Backend

- Python 3.14
- Flask
- Pandas
- NumPy
- Scikit-Learn
- Joblib
- PyODBC

### Database

- Microsoft SQL Server
- ODBC Driver 18

### Frontend

- HTML
- CSS
- JavaScript

---

## Project Architecture

```text
Finger Placement
       │
       ▼
MAX30102 Sensor
       │
       ▼
ESP32 WROOM-32
       │
       ▼
Feature Extraction
       │
       ▼
Flask API Server
       │
       ▼
Machine Learning Model
       │
       ▼
SQL Server Database
       │
       ▼
Web Dashboard + OLED Display
```

---

## Feature Extraction

The following features are extracted from PPG signals:

1. ir_mean
2. ir_ac
3. red_mean
4. red_ac
5. ratio
6. dc_ratio
7. perfusion_index
8. normalized_ir
9. heart_rate
10. signal_quality

These features are sent to the Machine Learning model for glucose prediction.

---

## Machine Learning Information

### Dataset

- 1200 synthetic PPG samples
- Realistic glucose-feature correlations

### Models Evaluated

- Ridge Regression
- Random Forest
- Support Vector Regression (SVR)
- Gradient Boosting Regressor

### Selected Model

```text
Gradient Boosting Regressor
```

### Performance

| Metric | Value |
|----------|----------|
| MAE | 14.64 mg/dL |
| RMSE | 19.23 mg/dL |
| R² Score | 0.7897 |
| Category Accuracy | 62.5% |

---

## Blood Group Prediction Disclaimer

Blood Group prediction is currently implemented as a research prototype feature.

The blood group displayed by the system should not be considered medically accurate or clinically validated.

Only glucose estimation, heart rate estimation, signal quality analysis, and dashboard monitoring are considered functional project components.

---

# How To Run The Project

## Step 1: Install Python Dependencies

Open terminal:

```bash
pip install flask pandas numpy scikit-learn joblib pyodbc
```

---

## Step 2: Configure SQL Server

Create database:

```sql
CREATE DATABASE bioscan;
```

Execute the database schema.

Update credentials inside:

```text
Backend/db_manager.py
```

Replace:

```python
SERVER = "YOUR_SERVER"
USERNAME = "YOUR_USERNAME"
PASSWORD = "YOUR_PASSWORD"
```

with your SQL Server details.

---

## Step 3: Run Machine Learning Pipeline

Run files in sequence:

### Generate Dataset

```bash
python step1_generate_dataset.py
```

### Train Model

```bash
python step2_train_model.py
```

### Evaluate Model

```bash
python step3_evaluate.py
```

### Start Flask Server

```bash
python step4_flask_server.py
```

You should see:

```text
Flask Server Running...
```

---

## Step 4: Configure Hotspot / WiFi

Open Arduino code.

Update:

```cpp
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";
```

The ESP32 must connect to the same WiFi/Hotspot used by the PC running Flask.

---

## Step 5: Update Flask Server IP

Find your PC IP:

```bash
ipconfig
```

Example:

```text
10.173.79.27
```

Update Arduino code:

```cpp
String serverUrl = "http://YOUR_PC_IP:5000/predict";
```

Example:

```cpp
String serverUrl = "http://10.173.79.27:5000/predict";
```

---

## Step 6: Upload Arduino Code

Open Arduino IDE.

Select:

```text
Board:
ESP32 WROOM DA Module
```

Select correct COM Port.

Click:

```text
Upload
```

Wait until upload completes successfully.

---

## Step 7: Open Serial Monitor

Baud Rate:

```text
115200
```

You should see:

```text
WiFi Connected
Server Connected
OLED Ready
```

---

## Step 8: Place Finger on Sensor

Place fingertip firmly on MAX30102.

System workflow:

```text
IDLE
 ↓
Finger Detection
 ↓
Signal Collection
 ↓
Feature Extraction
 ↓
Flask Prediction
 ↓
Database Logging
 ↓
OLED Display Result
 ↓
Dashboard Update
```

---

## OLED Display States

```text
Splash Screen
      ↓
Idle Screen
      ↓
Measuring Screen
      ↓
Analysing Screen
      ↓
Result Screen
      ↓
Back To Idle
```

---

## Dashboard Modules

- Patient Registration
- Patient Profile
- Smart Dashboard
- Recent Readings
- Historical Analysis
- SQL Database Records
- Live Monitoring

---

## Repository Structure

```text
Arduino_Code/
Backend/
Frontend/
Database/
Dataset/
Models/
Screenshots/
Documents/
README.md
```

---

## Research Prototype Notice

This project is intended for educational and research purposes only.

BioScan is not a medical device and should not be used for clinical diagnosis, treatment, or healthcare decision-making.

Glucose estimation results are generated using Machine Learning models trained on synthetic PPG datasets and should be considered experimental.

---

## Authors

| Sr. No. | Team Member Name |
|----------|------------------|
| 1 | Pruthviraj Sardar Patil |
| 2 | Rutvik Vijay Patil |
| 3 | Apurva Sanjay Deuskar |
| 4 | Tasmiya Akhtar Attar |
| 5 | Shashank Shashibhushan Kumbhar |

### Guided By

**Prof. Miss M. M. Pawar**

Department of Computer Science & Engineering
---

## Publication

Research Paper Published In:

**International Journal for Research in Applied Science & Engineering Technology (IJRASET)**

Volume 14, Issue 5, May 2026

Paper Title:

**BioScan: IoT Enabled Blood Group and Glucose Detection System Using Machine Learning**

---

## License

This project is released under the MIT License.
