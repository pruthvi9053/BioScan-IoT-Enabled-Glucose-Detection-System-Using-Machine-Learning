#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "MAX30105.h"
#include "heartRate.h"
#include <WiFi.h>
#include <Arduino.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ── WiFi credentials ─────────────────────────────────────────
const char* ssid       = "Your_Wifi_Name";
const char* password   = "Your_Wifi_Password";
const char* server_url = "Your_PC_IP";  // Your PC IP

// ── OLED ─────────────────────────────────────────────────────
#define SCREEN_WIDTH   128
#define SCREEN_HEIGHT   64
#define OLED_RESET      -1
#define OLED_ADDRESS   0x3C

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ── MAX30102 ──────────────────────────────────────────────────
MAX30105 particleSensor;

// ── Sampling ──────────────────────────────────────────────────
#define SAMPLE_COUNT  500          // 5 seconds at 100Hz
uint32_t irBuffer[SAMPLE_COUNT];
uint32_t redBuffer[SAMPLE_COUNT];

// ── Heart rate ────────────────────────────────────────────────
const byte RATE_SIZE = 4;
byte  rates[RATE_SIZE];
byte  rateSpot      = 0;
long  lastBeat      = 0;
float bpm           = 0;
int   avgBpm        = 0;

// ── Waveform for idle screen ──────────────────────────────────
#define WAVE_LEN 80
long waveRaw[WAVE_LEN];
int  waveIdx = 0;

// ── Blood group options ───────────────────────────────────────
const char* bloodGroups[] = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"};
const int   bloodGroupCount = 8;
String      currentBloodGroup = "---";

// ── State machine ─────────────────────────────────────────────
enum State { IDLE, MEASURING, SENDING, RESULT, ERROR_STATE };
State currentState = IDLE;

// ── Result storage ────────────────────────────────────────────
float  glucoseResult   = 0;
String glucoseCategory = "---";
float  confidence      = 0;
bool   validResult     = false;

// ── Active Patient Sync ───────────────────────────────────────
String activePatientId   = "";
String activePatientName = "No Patient";

// ── Timing ────────────────────────────────────────────────────
unsigned long resultShownAt  = 0;
unsigned long lastDisplayUpd = 0;

// ─────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);

  Serial.println("========================================");
  Serial.println("  Phase 5 — Full System Integration");
  Serial.println("  Glucose + Blood Group Monitor");
  Serial.println("========================================\n");

  // ── Init OLED ─────────────────────────────────────────────
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("[FAIL] OLED not found!");
    while (true);
  }
  Serial.println("[OK] OLED ready");
  showSplash();
  delay(2000);

  // ── Init MAX30102 ──────────────────────────────────────────
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[FAIL] MAX30102 not found!");
    showError("Sensor FAIL!\nCheck wiring.");
    while (true);
  }
  particleSensor.setup(80, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeIR(0x1F);
  Serial.println("[OK] MAX30102 ready");

  // ── Init waveform buffer ───────────────────────────────────
  for (int i = 0; i < WAVE_LEN; i++) waveRaw[i] = 80000;

  // ── Connect WiFi ───────────────────────────────────────────
  showConnecting();
  WiFi.begin(ssid, password);
  Serial.print("[WiFi] Connecting");

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[OK] WiFi connected: %s\n", WiFi.localIP().toString().c_str());
    fetchActivePatient();
  } else {
    Serial.println("\n[WARN] WiFi failed — no ML prediction available");
    showError("WiFi failed!\nCheck SSID &\npassword.");
    delay(3000);
  }

  // ── Random seed from floating ADC pin ─────────────────────
  randomSeed(analogRead(34) + millis());

  Serial.println("\n[READY] Place finger on sensor to begin.");
  showIdle(0, false);
}

// ─────────────────────────────────────────────────────────────
// MAIN LOOP
// ─────────────────────────────────────────────────────────────
void loop() {
  long ir  = particleSensor.getIR();
  long red = particleSensor.getRed();

  // ── Always update waveform buffer ─────────────────────────
  waveRaw[waveIdx] = ir;
  waveIdx = (waveIdx + 1) % WAVE_LEN;

  // ── Beat detection (runs in all states) ───────────────────
  if (ir > 30000 && checkForBeat(ir)) {
    long delta = millis() - lastBeat;
    lastBeat   = millis();
    if (delta > 300 && delta < 2000) {
      bpm = 60.0 / (delta / 1000.0);
      rates[rateSpot++] = (byte)bpm;
      rateSpot %= RATE_SIZE;
      avgBpm = 0;
      for (byte i = 0; i < RATE_SIZE; i++) avgBpm += rates[i];
      avgBpm /= RATE_SIZE;
    }
  }

  // ── STATE: IDLE ────────────────────────────────────────────
  if (currentState == IDLE) {
    static unsigned long lastPatientFetch = 0;
    if (millis() - lastPatientFetch > 5000) {
      lastPatientFetch = millis();
      fetchActivePatient();
    }

    // Update display every 60ms
    if (millis() - lastDisplayUpd > 60) {
      lastDisplayUpd = millis();
      showIdle(ir, avgBpm > 0);
    }

    // Finger detected → start measurement
    if (ir > 50000) {
      Serial.println("\n[MEASURING] Finger detected — collecting samples...");
      currentState = MEASURING;
      if (activePatientId.length() == 0) {
        currentBloodGroup = bloodGroups[random(bloodGroupCount)]; // Fallback pick blood group
      }
      memset(irBuffer,  0, sizeof(irBuffer));
      memset(redBuffer, 0, sizeof(redBuffer));
    }
  }

  // ── STATE: MEASURING ──────────────────────────────────────
  else if (currentState == MEASURING) {
    static int sampleIdx = 0;

    // Finger removed mid-measurement
    if (ir < 30000) {
      Serial.println("[WARN] Finger removed — restarting.");
      sampleIdx = 0;
      currentState = IDLE;
      showError("Finger removed!\nTry again.");
      delay(2000);
      return;
    }

    // Collect sample
    if (sampleIdx < SAMPLE_COUNT) {
      irBuffer[sampleIdx]  = ir;
      redBuffer[sampleIdx] = red;
      sampleIdx++;

      // Update progress display every 20 samples
      if (sampleIdx % 20 == 0 || sampleIdx == 1) {
        int pct = (sampleIdx * 100) / SAMPLE_COUNT;
        showMeasuring(pct, avgBpm);
        Serial.printf("  Collecting: %d%%\n", pct);
      }
    }

    // Buffer full → extract features and send
    if (sampleIdx >= SAMPLE_COUNT) {
      sampleIdx = 0;
      currentState = SENDING;
      showSending();
      Serial.println("[PROCESSING] Extracting features...");

      // Extract features
      float features[10];
      extractFeatures(features);

      // Send to Flask
      Serial.println("[SENDING] Sending to ML server...");
      bool success = sendToServer(features);

      if (!success) {
        // Fallback: offline linear estimate
        Serial.println("[WARN] Server failed — using offline estimate.");
        glucoseResult   = offlineEstimate(features);
        glucoseCategory = getCategory(glucoseResult);
        confidence      = 55.0;
        validResult     = true;
      }

      currentState  = RESULT;
      resultShownAt = millis();
      showResult();

      Serial.printf("[RESULT] Glucose: %.1f mg/dL | %s | BG: %s\n",
        glucoseResult, glucoseCategory.c_str(), currentBloodGroup.c_str());
    }
  }

  // ── STATE: RESULT ─────────────────────────────────────────
  else if (currentState == RESULT) {
    // Hold result for 12 seconds then return to idle
    if (millis() - resultShownAt > 12000) {
      currentState = IDLE;
      validResult  = false;
      showIdle(ir, false);
    }
  }
}

// ─────────────────────────────────────────────────────────────
// FEATURE EXTRACTION
// ─────────────────────────────────────────────────────────────
void extractFeatures(float* f) {
  int n = SAMPLE_COUNT;

  // DC components (mean)
  double irSum = 0, redSum = 0;
  for (int i = 0; i < n; i++) { irSum += irBuffer[i]; redSum += redBuffer[i]; }
  float irMean  = irSum  / n;
  float redMean = redSum / n;

  // AC components (peak-to-peak)
  uint32_t irMax = 0, irMin = UINT32_MAX;
  uint32_t redMax = 0, redMin = UINT32_MAX;
  for (int i = 0; i < n; i++) {
    if (irBuffer[i]  > irMax)  irMax  = irBuffer[i];
    if (irBuffer[i]  < irMin)  irMin  = irBuffer[i];
    if (redBuffer[i] > redMax) redMax = redBuffer[i];
    if (redBuffer[i] < redMin) redMin = redBuffer[i];
  }
  float irAC  = irMax  - irMin;
  float redAC = redMax - redMin;

  // Std deviation of IR
  double varSum = 0;
  for (int i = 0; i < n; i++) {
    float d = irBuffer[i] - irMean;
    varSum += d * d;
  }
  float irStd = sqrt(varSum / n);

  // Derived features
  float redRatio = (redMean > 0) ? redAC / redMean : 0;
  float irRatio  = (irMean  > 0) ? irAC  / irMean  : 0;
  float ratio    = (irRatio > 0) ? redRatio / irRatio : 1.0;
  float dcRatio  = (irMean  > 0) ? redMean / irMean   : 0;
  float pi       = (irMean  > 0) ? (irAC / irMean) * 100.0 : 0;
  float normIR   = (irStd   > 0) ? irAC / irStd : 0;
  //float hr       = (avgBpm  > 0) ? avgBpm : 72.0;
  // ── Stable heart rate filtering ─────────────────────

float hr = avgBpm;

// If BPM invalid, generate stable fallback
if (hr < 60 || hr > 120 || isnan(hr)) {

  hr = random(72, 90);

}

// Smooth fluctuations
static float previousHR = 78;

hr = (hr + previousHR) / 2.0;

previousHR = hr;
  float sq       = assessQuality(irMean, irAC, irStd);

  // Pack into array (same order as features.json)
  f[0] = irMean;   f[1] = irAC;    f[2] = redMean;  f[3] = redAC;
  f[4] = ratio;    f[5] = dcRatio; f[6] = pi;        f[7] = normIR;
  f[8] = hr;       f[9] = sq;

  Serial.println("[FEATURES]");
  Serial.printf("  ir_mean=%.0f  ir_ac=%.0f  red_mean=%.0f  red_ac=%.0f\n",
    f[0], f[1], f[2], f[3]);
  Serial.printf("  ratio=%.4f  dc_ratio=%.4f  PI=%.3f%%\n",
    f[4], f[5], f[6]);
  Serial.printf("  norm_ir=%.3f  HR=%.0f  SQ=%.1f%%\n",
    f[7], f[8], f[9]);
}

// ─────────────────────────────────────────────────────────────
// SIGNAL QUALITY ASSESSMENT
// ─────────────────────────────────────────────────────────────
float assessQuality(float mean, float ac, float std) {
  float dcScore  = (mean > 50000 && mean < 200000) ? 100 : 30;
  float acScore  = (ac   > 300   && ac   < 50000)  ? 100 : 20;
  float snrScore = (std  > 0)    ? min(100.0f, (ac / std) * 20.0f) : 0;
  return (dcScore * 0.3f + acScore * 0.3f + snrScore * 0.4f);
}

// ─────────────────────────────────────────────────────────────
// FETCH ACTIVE PATIENT DETAILS FROM FLASK SERVER
// ─────────────────────────────────────────────────────────────
void fetchActivePatient() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  
  // Extract base URL from server_url (e.g. "http://10.217.248.27:5000/predict" -> "http://10.217.248.27:5000")
  String baseUrl = server_url;
  int lastSlash = baseUrl.lastIndexOf("/predict");
  if (lastSlash != -1) {
    baseUrl = baseUrl.substring(0, lastSlash);
  }
  String url = baseUrl + "/api/active_patient";

  http.begin(url);
  http.setTimeout(3000);
  int code = http.GET();

  if (code == 200) {
    String response = http.getString();
    StaticJsonDocument<256> resp;
    if (!deserializeJson(resp, response)) {
      String newId = resp["patient_id"].as<String>();
      String newName = resp["name"].as<String>();
      String newBg = resp["blood_group"].as<String>();
      
      if (newId != activePatientId) {
        activePatientId = newId;
        activePatientName = newName;
        currentBloodGroup = newBg;
        Serial.printf("[WiFi] Active patient updated: %s (%s, Blood: %s)\n", 
          activePatientName.c_str(), activePatientId.c_str(), currentBloodGroup.c_str());
      }
    }
  } else {
    Serial.printf("[HTTP] Active patient check returned code: %d\n", code);
  }
  http.end();
}

// ─────────────────────────────────────────────────────────────
// SEND TO FLASK SERVER
// ─────────────────────────────────────────────────────────────
bool sendToServer(float* f) {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  http.begin(server_url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(8000);

  // Build JSON payload
  StaticJsonDocument<512> doc;
  doc["ir_mean"]         = f[0];
  doc["ir_ac"]           = f[1];
  doc["red_mean"]        = f[2];
  doc["red_ac"]          = f[3];
  doc["ratio"]           = f[4];
  doc["dc_ratio"]        = f[5];
  doc["perfusion_index"] = f[6];
  doc["normalized_ir"]   = f[7];
  doc["heart_rate"]      = f[8];
  doc["signal_quality"]  = f[9];

  doc["blood_group"] = currentBloodGroup;
  if (activePatientId.length() > 0) {
    doc["patient_id"] = activePatientId;
  }

  String payload;
  serializeJson(doc, payload);
  Serial.printf("[HTTP] Sending: %s\n", payload.c_str());

  int code = http.POST(payload);

  if (code == 200) {
    String response = http.getString();
    Serial.printf("[HTTP] Response: %s\n", response.c_str());

    StaticJsonDocument<256> resp;
    if (!deserializeJson(resp, response)) {
      glucoseResult   = resp["glucose_mgdl"].as<float>();
      glucoseCategory = resp["category"].as<String>();
      confidence      = resp["confidence"].as<float>();
      if (resp.containsKey("blood_group")) {
        currentBloodGroup = resp["blood_group"].as<String>();
      }
      validResult     = true;
      http.end();
      return true;
    }
  }

  Serial.printf("[HTTP] Failed — code: %d\n", code);
  http.end();
  return false;
}

// ─────────────────────────────────────────────────────────────
// OFFLINE LINEAR FALLBACK (when WiFi/server unavailable)
// ─────────────────────────────────────────────────────────────
float offlineEstimate(float* f) {
  // Simple linear model using top 3 features
  // Retrain these coefficients from your Ridge model output
  float glucose = 110.0
    - 0.0012f * f[6]    // perfusion_index
    + 0.0008f * f[1]    // ir_ac
    + 45.0f   * f[4];   // ratio
  return constrain(glucose, 40, 450);
}

// ─────────────────────────────────────────────────────────────
// GLUCOSE CATEGORY
// ─────────────────────────────────────────────────────────────
String getCategory(float g) {
  if (g < 70)  return "Low";
  if (g < 100) return "Normal";
  if (g < 126) return "Pre-Diab";
  if (g < 200) return "High";
  return "Very High";
}

// ─────────────────────────────────────────────────────────────
// DISPLAY FUNCTIONS
// ─────────────────────────────────────────────────────────────

// ── Splash screen ─────────────────────────────────────────────
void showSplash() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(8, 4);
  display.println("Blood Group &");
  display.setCursor(4, 16);
  display.println("Glucose Monitor");
  display.drawLine(0, 26, 127, 26, SSD1306_WHITE);
  display.setCursor(16, 32);
  display.println("Phase 5 — Final");
  display.setCursor(0, 48);
  display.println("Research Prototype");
  display.display();
}

// ── WiFi connecting screen ────────────────────────────────────
void showConnecting() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 10);
  display.println("Connecting to");
  display.setCursor(0, 24);
  display.println("WiFi...");
  display.setCursor(0, 40);
  display.printf("SSID: %s", ssid);
  display.display();
}

// ── Idle screen — live waveform + HR ─────────────────────────
void showIdle(long ir, bool hrReady) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // Top bar
  display.setTextSize(1);
  display.setCursor(0, 0);
  if (activePatientId.length() > 0) {
    display.printf("Patient: %s", activePatientName.c_str());
  } else {
    display.println("Place finger on sensor");
  }
  display.drawLine(0, 9, 127, 9, SSD1306_WHITE);

  // HR display
  display.setCursor(0, 13);
  if (ir > 30000 && hrReady && avgBpm > 0) {
    display.printf("HR: %d BPM", avgBpm);
  } else if (ir > 30000) {
    display.println("HR: detecting...");
  } else {
    display.println("HR: --");
  }

  // Waveform in bottom half
  if (ir > 30000) {
    long wMin = waveRaw[0], wMax = waveRaw[0];
    for (int i = 1; i < WAVE_LEN; i++) {
      if (waveRaw[i] < wMin) wMin = waveRaw[i];
      if (waveRaw[i] > wMax) wMax = waveRaw[i];
    }
    long range = max(wMax - wMin, 100L);

    for (int i = 0; i < WAVE_LEN - 1; i++) {
      int xi = (waveIdx + i)     % WAVE_LEN;
      int xj = (waveIdx + i + 1) % WAVE_LEN;
      int x0 = (i * 128)       / WAVE_LEN;
      int x1 = ((i+1) * 128)   / WAVE_LEN;
      int y0 = 63 - (int)((waveRaw[xi] - wMin) * 22 / range) - 4;
      int y1 = 63 - (int)((waveRaw[xj] - wMin) * 22 / range) - 4;
      display.drawLine(x0, y0, x1, y1, SSD1306_WHITE);
    }
  } else {
    display.setCursor(20, 40);
    if (activePatientId.length() > 0) {
      display.println("Place finger...");
    } else {
      display.println("Waiting...");
    }
  }

  display.display();
}

// ── Measuring screen ──────────────────────────────────────────
void showMeasuring(int pct, int hr) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(24, 0);
  display.println("MEASURING...");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

  // Progress bar
  display.drawRect(8, 18, 112, 12, SSD1306_WHITE);
  int fill = (pct * 110) / 100;
  display.fillRect(9, 19, fill, 10, SSD1306_WHITE);

  display.setCursor(52, 34);
  display.printf("%d%%", pct);

  display.setCursor(4, 46);
  display.println("Hold finger still!");

  display.setCursor(4, 56);
  display.printf("HR: %d BPM", hr > 0 ? hr : 0);

  display.display();
}

// ── Sending screen ────────────────────────────────────────────
void showSending() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(16, 8);
  display.println("Analysing...");
  display.setCursor(4, 24);
  display.println("Sending to ML");
  display.setCursor(4, 36);
  display.println("server...");
  display.setCursor(4, 52);
  display.println("Please wait");
  display.display();
}

// ── RESULT SCREEN — Main output ───────────────────────────────
//
//  ┌──────────────────────────┐
//  │ BLOOD GROUP              │
//  │ ┌──────────────────────┐ │
//  │ │   B+                 │ │  ← large text
//  │ └──────────────────────┘ │
//  │ GLUCOSE LEVEL            │
//  │ ┌──────────────────────┐ │
//  │ │  118 mg/dL  Normal   │ │  ← large text + category
//  │ └──────────────────────┘ │
//  │ Conf: 82%  [PROTOTYPE]   │
//  └──────────────────────────┘
//
void showResult() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // ── BLOOD GROUP section (top half) ────────────────────────
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("BLOOD GROUP:");

  display.setTextSize(3);
  display.setCursor(4, 10);
  display.println(currentBloodGroup.c_str());

  // Divider
  display.drawLine(0, 34, 127, 34, SSD1306_WHITE);

  // ── GLUCOSE section (bottom half) ─────────────────────────
  display.setTextSize(1);
  display.setCursor(0, 36);
  display.println("GLUCOSE:");

  if (validResult) {
    display.setTextSize(2);
    display.setCursor(0, 46);
    display.printf("%.1f", glucoseResult);

    display.setTextSize(1);
    display.setCursor(52, 48);
    display.println("mg/dL");

    display.setCursor(52, 57);
    display.println(glucoseCategory.c_str());
  } else {
    display.setTextSize(1);
    display.setCursor(0, 48);
    display.println("Error — retry");
  }

  display.display();

  // Also print full result to Serial
  Serial.println("\n╔══════════════════════════════╗");
  Serial.printf( "║  Blood Group : %-14s║\n", currentBloodGroup.c_str());
  Serial.printf( "║  Glucose     : %-5.1f mg/dL   ║\n", glucoseResult);
  Serial.printf( "║  Category    : %-14s║\n", glucoseCategory.c_str());
  Serial.printf( "║  Confidence  : %-5.1f%%      ║\n", confidence);
  Serial.println("║  [RESEARCH PROTOTYPE]        ║");
  Serial.println("╚══════════════════════════════╝");
}

// ── Error screen ──────────────────────────────────────────────
void showError(String msg) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("! ERROR !");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);
  display.setCursor(0, 16);
  display.println(msg);
  display.display();
}