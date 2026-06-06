# ============================================================
# BIOSCAN DATABASE MANAGER
# ============================================================
# This module provides a unified database interface for BioScan.
# It attempts to connect to a local Microsoft SQL Server instance.
# If SQL Server is unavailable (missing drivers, wrong credentials,
# or database server stopped), it automatically and gracefully
# falls back to a local SQLite database (database/bioscan.db).
# ============================================================

import os
import re
import random
import sqlite3
from datetime import datetime

# Try importing pyodbc for SQL Server
try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False

# ── DATABASE CONFIGURATION ────────────────────────────────────
# You can customize these settings to match your local SQL Server instance.
SQL_SERVER_CONFIG = {
    'server': 'YOUR_SQL_SERVER', # Target your active named SQLEXPRESS instance
    'database': 'bioscan',             # Database name
    'trusted_connection': 'yes',       # 'yes' for Windows Auth, 'no' for SQL Auth
    'username': 'YOUR_USERNAME',                    # Required only if trusted_connection is 'no'
    'password': 'YOUR_PASSWORD',                    # Required only if trusted_connection is 'no'
    'driver': None                     # Set to a specific driver name, or let the manager auto-detect
}

BLOOD_GROUPS = ["A+", "B+", "O+", "AB+", "A-", "B-", "O-", "AB-"]

class DatabaseManager:
    def __init__(self):
        self.is_mssql = False
        self.conn = None
        self.db_type_label = "SQLite (Fallback)"
        self.error_message = None
        
        # 1. Try to connect to Microsoft SQL Server
        if PYODBC_AVAILABLE:
            try:
                self._connect_mssql()
            except Exception as e:
                self.error_message = str(e)
                print(f"\n  [DATABASE WARNING] Could not connect to SQL Server. Details: {e}")
                print("  [DATABASE INFO] Falling back to local SQLite database...")
        else:
            self.error_message = "pyodbc library is not installed."
            print("\n  [DATABASE WARNING] pyodbc is not installed. Run 'pip install pyodbc' to use SQL Server.")
            print("  [DATABASE INFO] Falling back to local SQLite database...")

        # 2. If MSSQL connection failed or pyodbc not available, connect to SQLite
        if not self.conn:
            self._connect_sqlite()

        # 3. Create tables if they do not exist
        self._initialize_tables()

    def _connect_mssql(self):
        """Attempts to discover drivers and connect to Microsoft SQL Server."""
        # Discover available ODBC drivers
        drivers = [d for d in pyodbc.drivers() if 'SQL Server' in d or 'ODBC Driver' in d]
        if not drivers:
            raise Exception("No SQL Server ODBC drivers found on this system. Install Microsoft ODBC Driver for SQL Server.")

        # Pick the best/most recent driver
        selected_driver = SQL_SERVER_CONFIG['driver']
        if not selected_driver:
            # Prefer 'ODBC Driver 18/17 for SQL Server' over older drivers
            preferred = sorted([d for d in drivers if 'ODBC Driver' in d], reverse=True)
            selected_driver = preferred[0] if preferred else drivers[0]

        print(f"  [DB DISCOVERY] Found SQL Server drivers: {drivers}")
        print(f"  [DB DISCOVERY] Using driver: {selected_driver}")

        # Connection parameters
        srv = SQL_SERVER_CONFIG['server']
        db_name = SQL_SERVER_CONFIG['database']
        trusted = SQL_SERVER_CONFIG['trusted_connection']
        
        # Step A: Connect to 'master' database first to ensure target database exists
        print(f"  [DB CONNECTING] Connecting to SQL Server '{srv}' (master database) to check/create '{db_name}'...")
        if trusted.lower() == 'yes':
            master_conn_str = f"DRIVER={{{selected_driver}}};SERVER={srv};DATABASE=master;Trusted_Connection=yes;Encrypt=no;"
        else:
            usr = SQL_SERVER_CONFIG['username']
            pwd = SQL_SERVER_CONFIG['password']
            master_conn_str = f"DRIVER={{{selected_driver}}};SERVER={srv};DATABASE=master;UID={usr};PWD={pwd};Encrypt=no;"
        
        # In case driver 18 needs TrustServerCertificate=yes
        if 'ODBC Driver 18' in selected_driver:
            master_conn_str += "TrustServerCertificate=yes;"

        master_conn = pyodbc.connect(master_conn_str, timeout=3)
        master_conn.autocommit = True
        master_cursor = master_conn.cursor()
        
        # Check if database exists
        master_cursor.execute("SELECT database_id FROM sys.databases WHERE name = ?", (db_name,))
        row = master_cursor.fetchone()
        if not row:
            print(f"  [DB CREATION] Database '{db_name}' does not exist on SQL Server. Creating it now...")
            master_cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"  [DB CREATION] Database '{db_name}' created successfully.")
        
        master_cursor.close()
        master_conn.close()

        # Step B: Connect to the actual target database
        print(f"  [DB CONNECTING] Connecting to SQL Server database '{db_name}'...")
        conn_str = master_conn_str.replace("DATABASE=master", f"DATABASE={db_name}")
        
        self.conn = pyodbc.connect(conn_str, timeout=5)
        self.conn.autocommit = True  # Auto-commit queries
        self.is_mssql = True
        self.db_type_label = f"Microsoft SQL Server (via {selected_driver})"
        print(f"  [DATABASE SUCCESS] Connected to {self.db_type_label}!")

    def _connect_sqlite(self):
        """Connects to the local SQLite database, creating directories if needed."""
        os.makedirs('database', exist_ok=True)
        db_path = os.path.join('database', 'bioscan.db')
        print(f"  [DB CONNECTING] Connecting to SQLite local database at '{db_path}'...")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.is_mssql = False
        self.db_type_label = "SQLite Database File"
        print("  [DATABASE SUCCESS] Connected to SQLite local database!")

    def _initialize_tables(self):
        """Creates the Patients and Readings tables if they do not exist."""
        cursor = self.conn.cursor()
        
        # Auto-migration check: If Patients table exists but PatientID column is TEXT/NVARCHAR, safely recreate
        schema_mismatch = False
        try:
            if self.is_mssql:
                # Query column type in Microsoft SQL Server info schema
                cursor.execute("""
                    SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'Patients' AND COLUMN_NAME = 'PatientID'
                """)
                row = cursor.fetchone()
                if row and 'char' in row[0].lower():
                    schema_mismatch = True
            else:
                # Check if Patients table exists first in SQLite
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Patients'")
                if cursor.fetchone():
                    # Query column type in SQLite info schema
                    cursor.execute("PRAGMA table_info(Patients)")
                    cols = cursor.fetchall()
                    for c in cols:
                        if c[1] == 'PatientID' and 'text' in c[2].lower():
                            schema_mismatch = True
                            break
        except Exception as e:
            print(f"  [DB MIGRATION CHECK ERROR] {e}")

        if schema_mismatch:
            print("\n  [DB MIGRATION REQUIRED] Old TEXT/NVARCHAR schema detected for PatientID.")
            print("  [DB MIGRATION ACTION] Safely dropping tables and recreating them with autoincrementing INTEGER keys...")
            try:
                if self.is_mssql:
                    cursor.execute("DROP TABLE IF EXISTS Readings")
                    cursor.execute("DROP TABLE IF EXISTS Patients")
                else:
                    cursor.execute("DROP TABLE IF EXISTS Readings")
                    cursor.execute("DROP TABLE IF EXISTS Patients")
                    self.conn.commit()
                print("  [DB MIGRATION SUCCESS] Old tables dropped cleanly.")
            except Exception as e:
                print(f"  [DB MIGRATION ERROR] Could not drop old tables: {e}")
        
        if self.is_mssql:
            # SQL Server schemas
            cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Patients')
            CREATE TABLE Patients (
                PatientID INT IDENTITY(1,1) PRIMARY KEY,
                Name NVARCHAR(100) NOT NULL,
                Age INT NOT NULL,
                Weight DECIMAL(5, 2) NOT NULL,
                Gender NVARCHAR(20) NOT NULL,
                BloodGroup NVARCHAR(5) NOT NULL,
                CreatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Readings')
            CREATE TABLE Readings (
                ReadingID INT IDENTITY(1,1) PRIMARY KEY,
                PatientID INT NOT NULL,
                GlucoseMGDL DECIMAL(5, 1) NOT NULL,
                Category NVARCHAR(50) NOT NULL,
                Confidence DECIMAL(5, 1) NOT NULL,
                HeartRate DECIMAL(5, 1) NOT NULL,
                Timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                IRMean DECIMAL(12, 2),
                IRAC DECIMAL(12, 2),
                RedMean DECIMAL(12, 2),
                RedAC DECIMAL(12, 2),
                Ratio DECIMAL(10, 4),
                DCRatio DECIMAL(10, 4),
                PerfusionIndex DECIMAL(10, 4),
                NormalizedIR DECIMAL(10, 4),
                SignalQuality DECIMAL(5, 1),
                FOREIGN KEY (PatientID) REFERENCES Patients(PatientID) ON DELETE CASCADE
            )
            """)
        else:
            # SQLite schemas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Patients (
                PatientID INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                Age INTEGER NOT NULL,
                Weight REAL NOT NULL,
                Gender TEXT NOT NULL,
                BloodGroup TEXT NOT NULL,
                CreatedAt TEXT DEFAULT (datetime('now', 'localtime'))
            )
            """)
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS Readings (
                ReadingID INTEGER PRIMARY KEY AUTOINCREMENT,
                PatientID INTEGER NOT NULL,
                GlucoseMGDL REAL NOT NULL,
                Category TEXT NOT NULL,
                Confidence REAL NOT NULL,
                HeartRate REAL NOT NULL,
                Timestamp TEXT DEFAULT (datetime('now', 'localtime')),
                IRMean REAL,
                IRAC REAL,
                RedMean REAL,
                RedAC REAL,
                Ratio REAL,
                DCRatio REAL,
                PerfusionIndex REAL,
                NormalizedIR REAL,
                SignalQuality REAL,
                FOREIGN KEY (PatientID) REFERENCES Patients(PatientID) ON DELETE CASCADE
            )
            """)
            self.conn.commit()
            
        cursor.close()
        print("  [DATABASE INFO] Tables validated and initialized.")

    def _slugify(self, text):
        """Converts name to a simple ID slug (e.g. 'John Doe' -> 'john-doe')."""
        text = text.strip().lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        return re.sub(r'[\s-]+', '-', text)

    def register_or_get_patient(self, name, age, weight, gender):
        """Registers a new patient profile or returns existing if found."""
        cursor = self.conn.cursor()
        
        # Check if patient exists by name case-insensitively
        if self.is_mssql:
            cursor.execute("SELECT PatientID, Name, Age, Weight, Gender, BloodGroup FROM Patients WHERE LOWER(Name) = LOWER(?)", (name,))
        else:
            cursor.execute("SELECT PatientID, Name, Age, Weight, Gender, BloodGroup FROM Patients WHERE LOWER(Name) = LOWER(?)", (name,))
            
        row = cursor.fetchone()
        
        if row:
            # Patient exists, return profile details
            profile = {
                'patient_id': int(row[0]),
                'name': row[1],
                'age': int(row[2]),
                'weight': float(row[3]),
                'gender': row[4],
                'blood_group': row[5],
                'status': 'existing'
            }
        else:
            # Patient doesn't exist, create a new profile with empty Blood Group placeholder
            blood_group = "---"
            
            if self.is_mssql:
                cursor.execute("""
                    INSERT INTO Patients (Name, Age, Weight, Gender, BloodGroup)
                    OUTPUT INSERTED.PatientID
                    VALUES (?, ?, ?, ?, ?)
                """, (name, age, weight, gender, blood_group))
                inserted_id = int(cursor.fetchone()[0])
            else:
                cursor.execute("""
                    INSERT INTO Patients (Name, Age, Weight, Gender, BloodGroup)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, age, weight, gender, blood_group))
                self.conn.commit()
                # Retrieve SQLite autoincremented ID
                inserted_id = int(cursor.lastrowid)
                
            profile = {
                'patient_id': inserted_id,
                'name': name,
                'age': int(age),
                'weight': float(weight),
                'gender': gender,
                'blood_group': blood_group,
                'status': 'created'
            }
            print(f"  [DB PROFILE] Registered patient profile for '{name}' (ID: {inserted_id}) with Blood Type: {blood_group}")
            
        cursor.close()
        return profile

    def add_reading(self, patient_id, glucose, category, confidence, heart_rate, raw_features=None):
        """Inserts a new telemetry reading in the database."""
        if not raw_features:
            raw_features = {}
            
        try:
            patient_id = int(patient_id)
        except (ValueError, TypeError):
            pass

        cursor = self.conn.cursor()
        
        # Update patient's blood group if it's sent in raw_features/telemetry and is valid
        if raw_features and 'blood_group' in raw_features:
            bg = raw_features['blood_group']
            if bg and bg != '---' and bg in BLOOD_GROUPS:
                cursor.execute("UPDATE Patients SET BloodGroup = ? WHERE PatientID = ?", (bg, patient_id))
                if not self.is_mssql:
                    self.conn.commit()
        
        params = (
            patient_id,
            float(glucose),
            category,
            float(confidence),
            float(heart_rate),
            raw_features.get('ir_mean'),
            raw_features.get('ir_ac'),
            raw_features.get('red_mean'),
            raw_features.get('red_ac'),
            raw_features.get('ratio'),
            raw_features.get('dc_ratio'),
            raw_features.get('perfusion_index'),
            raw_features.get('normalized_ir'),
            raw_features.get('signal_quality')
        )
        
        if self.is_mssql:
            cursor.execute("""
                INSERT INTO Readings (
                    PatientID, GlucoseMGDL, Category, Confidence, HeartRate,
                    IRMean, IRAC, RedMean, RedAC, Ratio, DCRatio, PerfusionIndex, NormalizedIR, SignalQuality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, params)
        else:
            cursor.execute("""
                INSERT INTO Readings (
                    PatientID, GlucoseMGDL, Category, Confidence, HeartRate,
                    IRMean, IRAC, RedMean, RedAC, Ratio, DCRatio, PerfusionIndex, NormalizedIR, SignalQuality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, params)
            self.conn.commit()
            
        cursor.close()
        print(f"  [DB TELEMETRY] Logged reading to database for patient ID '{patient_id}': {glucose} mg/dL ({category})")

    def get_history(self, patient_id, limit=10):
        """Fetches the latest readings for a patient in descending order."""
        try:
            patient_id = int(patient_id)
        except (ValueError, TypeError):
            pass

        cursor = self.conn.cursor()
        
        query = """
            SELECT GlucoseMGDL, Category, Confidence, HeartRate, Timestamp 
            FROM Readings 
            WHERE PatientID = ? 
            ORDER BY ReadingID DESC
        """
        
        # Apply row limits based on SQL dialect
        if self.is_mssql:
            cursor.execute(f"SELECT TOP {limit} GlucoseMGDL, Category, Confidence, HeartRate, Timestamp FROM Readings WHERE PatientID = ? ORDER BY ReadingID DESC", (patient_id,))
        else:
            cursor.execute(query + f" LIMIT {limit}", (patient_id,))
            
        rows = cursor.fetchall()
        cursor.close()
        
        history = []
        for r in rows:
            # Handle timestamps. SQL Server returns datetime objects. SQLite returns strings.
            ts = r[4]
            if isinstance(ts, datetime):
                formatted_time = ts.strftime("%I:%M:%S %p")
            else:
                try:
                    # Parse SQLite format: "YYYY-MM-DD HH:MM:SS"
                    parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    formatted_time = parsed.strftime("%I:%M:%S %p")
                except:
                    formatted_time = str(ts)
                    
            history.append({
                'glucose': float(r[0]),
                'category': r[1],
                'confidence': float(r[2]),
                'heart_rate': float(r[3]),
                'time': formatted_time
            })
            
        return history

    def get_patient_details_and_stats(self, patient_id):
        """Fetches patient profile along with dynamic diagnostic statistics from readings database."""
        try:
            patient_id = int(patient_id)
        except (ValueError, TypeError):
            pass

        cursor = self.conn.cursor()
        
        # 1. Fetch patient profile details
        if self.is_mssql:
            cursor.execute("SELECT PatientID, Name, Age, Weight, Gender, BloodGroup, CreatedAt FROM Patients WHERE PatientID = ?", (patient_id,))
        else:
            cursor.execute("SELECT PatientID, Name, Age, Weight, Gender, BloodGroup, CreatedAt FROM Patients WHERE PatientID = ?", (patient_id,))
            
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return None
            
        # Format registration timestamp cleanly
        ts = row[6]
        if isinstance(ts, datetime):
            formatted_date = ts.strftime("%B %d, %Y")
        else:
            try:
                # Parse SQLite datetime format: "YYYY-MM-DD HH:MM:SS" or similar
                parsed = datetime.strptime(str(ts).split(".")[0], "%Y-%m-%d %H:%M:%S")
                formatted_date = parsed.strftime("%B %d, %Y")
            except:
                formatted_date = str(ts)

        profile = {
            'patient_id': int(row[0]),
            'name': row[1],
            'age': int(row[2]),
            'weight': float(row[3]),
            'gender': row[4],
            'blood_group': row[5],
            'created_at': formatted_date,
            'stats': {}
        }
        
        # 2. Fetch aggregated calculations on telemetry readings
        query = """
            SELECT 
                COUNT(*) as total_readings,
                AVG(GlucoseMGDL) as avg_glucose,
                MIN(GlucoseMGDL) as min_glucose,
                MAX(GlucoseMGDL) as max_glucose,
                AVG(HeartRate) as avg_heart_rate
            FROM Readings
            WHERE PatientID = ?
        """
        cursor.execute(query, (patient_id,))
        stats_row = cursor.fetchone()
        
        if stats_row and stats_row[0] > 0:
            profile['stats'] = {
                'total_readings': int(stats_row[0]),
                'avg_glucose': round(float(stats_row[1]), 1),
                'min_glucose': round(float(stats_row[2]), 1),
                'max_glucose': round(float(stats_row[3]), 1),
                'avg_heart_rate': round(float(stats_row[4]), 1)
            }
        else:
            profile['stats'] = {
                'total_readings': 0,
                'avg_glucose': 0,
                'min_glucose': 0,
                'max_glucose': 0,
                'avg_heart_rate': 0
            }
            
        cursor.close()
        return profile

    def close(self):
        """Safely closes connections."""
        if self.conn:
            self.conn.close()
            self.conn = None
            print("  [DATABASE INFO] Database connections closed.")

