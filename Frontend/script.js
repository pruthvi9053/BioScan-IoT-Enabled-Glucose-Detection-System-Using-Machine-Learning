console.log("BioScan Dashboard Loaded");

/* ───────────────────────────────────── */
/* DOM & VIEW INITIALIZATION */
/* ───────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
    const profileJson = localStorage.getItem("patientProfile");

    if (profileJson) {
        try {
            const profile = JSON.parse(profileJson);
            // Pre-fill the form input fields with the last registered patient's details
            const nameInput = document.getElementById("inputName");
            const ageInput = document.getElementById("inputAge");
            const weightInput = document.getElementById("inputWeight");
            const genderInput = document.getElementById("inputGender");

            if (nameInput && profile.name) nameInput.value = profile.name;
            if (ageInput && profile.age) ageInput.value = profile.age;
            if (weightInput && profile.weight) weightInput.value = profile.weight;
            if (genderInput && profile.gender) genderInput.value = profile.gender;

            // Load initial demographics on the UI so if they proceed, everything matches
            updatePatientUI(profile);
            updateDbStatus(profile.db_type);
        } catch (e) {
            console.error("Failed to parse stored patient profile:", e);
            localStorage.removeItem("patientProfile");
        }
    }
    
    // Always show the 1st page (Patient Registration Form) on page load
    showRegistrationForm();
});

function showRegistrationForm() {
    document.getElementById("formView").classList.remove("hidden-view");
    document.getElementById("dashboardView").classList.add("hidden-view");
}

function updatePatientUI(profile) {
    const nameEl = document.getElementById("patientName");
    const ageEl = document.getElementById("patientAge");
    const weightEl = document.getElementById("patientWeight");
    const genderEl = document.getElementById("patientGender");
    const bloodGroupCardEl = document.getElementById("bloodGroupCard");
    const avatarEl = document.querySelector(".avatar");

    if (nameEl) nameEl.innerText = profile.name;
    if (ageEl) ageEl.innerText = profile.age;
    if (weightEl) weightEl.innerText = `${profile.weight} KG`;
    if (genderEl) genderEl.innerText = profile.gender;
    if (bloodGroupCardEl) bloodGroupCardEl.innerText = profile.blood_group || "---";
    
    const dashboardPatientIDEl = document.getElementById("dashboardPatientID");
    if (dashboardPatientIDEl && profile.patient_id) {
        dashboardPatientIDEl.innerText = profile.patient_id;
    }
 
    if (avatarEl && profile.name) {
        avatarEl.innerText = profile.name.trim().charAt(0).toUpperCase();
    }
}

function updateDbStatus(dbLabel) {
    const dbStatusBadge = document.getElementById("dbStatusBadge");
    if (dbStatusBadge) {
        const isOffline = dbLabel && (dbLabel.includes('Offline') || dbLabel.includes('Fallback'));
        dbStatusBadge.innerHTML = `
            <span class="online-dot" style="background: ${isOffline ? '#0077b6' : '#22c55e'};"></span>
            DB: ${dbLabel || 'SQLite'}
        `;
    }
}

function showDashboardView(animate = true) {
    const formView = document.getElementById("formView");
    const dashboardView = document.getElementById("dashboardView");

    if (animate) {
        formView.classList.add("fade-out");
        setTimeout(() => {
            formView.classList.add("hidden-view");
            dashboardView.classList.remove("hidden-view");
            dashboardView.classList.add("fade-in");
            
            updateDashboard();
        }, 500);
    } else {
        formView.classList.add("hidden-view");
        dashboardView.classList.remove("hidden-view");
        
        updateDashboard();
    }
}

async function proceedToDashboard() {
    const name = document.getElementById("inputName").value.trim();
    const age = parseInt(document.getElementById("inputAge").value);
    const weight = parseFloat(document.getElementById("inputWeight").value);
    const gender = document.getElementById("inputGender").value;

    if (!name || !age || !weight || !gender) {
        alert("Please fill out all patient details.");
        return;
    }

    try {
        const response = await fetch('/api/patients', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, age, weight, gender })
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || 'Failed to register patient');
        }
        
        const profile = await response.json();
        
        // Save details to LocalStorage
        localStorage.setItem("patientProfile", JSON.stringify(profile));

        // Update patient information card
        updatePatientUI(profile);
        updateDbStatus(profile.db_type);

        // Smooth transition
        showDashboardView(true);
    } catch (error) {
        console.warn("Could not reach backend API for registration, running in offline mode:", error);
        
        // Pull an integer ID via localStorage.getItem("lastOfflinePatientId"), incrementing by 1 sequentially
        let lastOfflineId = localStorage.getItem("lastOfflinePatientId");
        let nextOfflineId = 1;
        if (lastOfflineId) {
            nextOfflineId = parseInt(lastOfflineId, 10) + 1;
        }
        localStorage.setItem("lastOfflinePatientId", nextOfflineId);
        
        // Fallback to local offline mode so UX doesn't freeze
        const offlineProfile = {
            patient_id: nextOfflineId,
            name: name,
            age: age,
            weight: weight,
            gender: gender,
            blood_group: "---",
            db_type: "SQLite (Fallback / Offline)"
        };
        localStorage.setItem("patientProfile", JSON.stringify(offlineProfile));
        updatePatientUI(offlineProfile);
        updateDbStatus(offlineProfile.db_type);
        showDashboardView(true);
    }
}


/* ───────────────────────────────────── */
/* FETCH & UPDATE DASHBOARD VALUES */
/* ───────────────────────────────────── */

async function updateDashboard() {
    const profileJson = localStorage.getItem("patientProfile");
    if (!profileJson) return;

    let profile;
    try {
        profile = JSON.parse(profileJson);
    } catch (e) {
        return;
    }

    // Check which view is currently active and update it dynamically
    const dashboardSec = document.getElementById("dashboardSection");
    const patientInfoSec = document.getElementById("patientInfoSection");
    const reportsSec = document.getElementById("reportsSection");

    if (dashboardSec && !dashboardSec.classList.contains("hidden-view")) {
        try {
            // Fetch telemetry history from database
            const response = await fetch(`/api/history/${profile.patient_id}`);
            if (!response.ok) throw new Error("Failed to load telemetry history");
            
            const data = await response.json();
            
            if (data.db_type) {
                updateDbStatus(data.db_type);
            }

            // Update blood group dynamically on the dashboard card
            const bloodGroupCardEl = document.getElementById("bloodGroupCard");
            if (bloodGroupCardEl && data.blood_group) {
                bloodGroupCardEl.innerText = data.blood_group;
            }

            const history = data.history || [];
            if (history.length > 0) {
                // Retrieve latest telemetry reading
                const latest = history[0];
                
                const glucoseValEl = document.getElementById("glucoseValue");
                if (glucoseValEl) glucoseValEl.innerHTML = `${parseFloat(latest.glucose).toFixed(1)}`;

                const glucoseCatEl = document.getElementById("glucoseCategory");
                if (glucoseCatEl) {
                    glucoseCatEl.innerText = latest.category;
                    // Strip previous classes and apply current
                    glucoseCatEl.className = "badge " + latest.category.toLowerCase().replace(" ", "-");
                }

                const hrValEl = document.getElementById("heartRate");
                if (hrValEl) hrValEl.innerHTML = `${parseFloat(latest.heart_rate).toFixed(1)}`;

                const confidenceValEl = document.getElementById("confidence");
                if (confidenceValEl) confidenceValEl.innerHTML = `${latest.confidence}%`;
            }

            // Draw readings history table
            renderHistoryTable(history);

            // Calculate and animate the clinical Bio-Health Score dynamically
            calculateAndUpdateHealthScore(history);

        } catch (error) {
            console.error("Dashboard database update failed:", error);
        }
    } else if (patientInfoSec && !patientInfoSec.classList.contains("hidden-view")) {
        // Auto-refresh patient info stats and history in real-time
        loadPatientInfoAndStats();
    } else if (reportsSec && !reportsSec.classList.contains("hidden-view")) {
        // Auto-refresh patient reports stats and history in real-time
        loadPatientReportData();
    }
}

/* ───────────────────────────────────── */
/* HISTORY TABLE RENDER */
/* ───────────────────────────────────── */

function renderHistoryTable(history) {
    const tbody = document.getElementById("historyBody");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (history.length === 0) {
        const row = tbody.insertRow();
        const cell = row.insertCell(0);
        cell.colSpan = 5;
        cell.innerHTML = "<em style='color: #64748b;'>No telemetry logs found in database. Please connect IoT device to start recording.</em>";
        cell.style.padding = "20px";
        return;
    }

    history.forEach(item => {
        const row = tbody.insertRow();
        
        row.insertCell(0).innerHTML = item.time;
        row.insertCell(1).innerHTML = `<strong>${parseFloat(item.glucose).toFixed(1)}</strong>`;
        
        let catClass = "normal";
        const cat = item.category.toLowerCase();
        if (cat.includes("high")) catClass = "high";
        else if (cat.includes("pre-diabetic")) catClass = "pre-diabetic";
        
        row.insertCell(2).innerHTML = `<span class="badge ${catClass}" style="margin-top:0; padding:4px 12px; font-size:12px;">${item.category}</span>`;
        row.insertCell(3).innerHTML = `${parseFloat(item.heart_rate).toFixed(1)} BPM`;
        row.insertCell(4).innerHTML = `${item.confidence}%`;
    });
}

/* ───────────────────────────────────── */
/* DYNAMIC CLINICAL HEALTH SCORE CALCULATOR */
/* ───────────────────────────────────── */

function calculateAndUpdateHealthScore(history) {
    const scoreCircle = document.getElementById("scoreCircle");
    const scoreNumber = document.getElementById("scoreNumber");
    const scoreStatus = document.getElementById("scoreStatus");
    if (!scoreCircle || !scoreNumber || !scoreStatus) return;

    let score = 95; // Default baseline score
    let statusText = "Optimal";
    let statusClass = "status-optimal";
    let color = "#22c55e"; // green

    if (history && history.length > 0) {
        const latest = history[0];
        const glucose = parseFloat(latest.glucose);
        const heartRate = parseFloat(latest.heart_rate);
        const confidence = parseFloat(latest.confidence);

        // Deduct points based on glucose level deviation
        // Optimal clinical range: 70 - 110 mg/dL
        if (glucose < 70) {
            const dev = 70 - glucose;
            score -= dev * 0.8;
        } else if (glucose > 110) {
            const dev = glucose - 110;
            score -= dev * 0.5;
        }

        // Deduct points based on heart rate deviation
        // Optimal range: 60 - 90 BPM
        if (heartRate < 60) {
            const dev = 60 - heartRate;
            score -= dev * 0.4;
        } else if (heartRate > 90) {
            const dev = heartRate - 90;
            score -= dev * 0.4;
        }

        // Deduct points slightly if confidence is less than 95%
        if (confidence < 95) {
            score -= (95 - confidence) * 0.15;
        }

        // Round score and constrain between 45 and 100
        score = Math.max(45, Math.min(100, Math.round(score)));

        // Determine status labels and colors
        if (score >= 90) {
            statusText = "Optimal";
            statusClass = "status-optimal";
            color = "#22c55e";
        } else if (score >= 75) {
            statusText = "Stable";
            statusClass = "status-warning";
            color = "#f59e0b";
        } else {
            statusText = "Needs Review";
            statusClass = "status-alert";
            color = "#ef4444";
        }
    } else {
        // Baseline default
        score = 98;
        statusText = "Baseline";
        statusClass = "status-optimal";
        color = "#22c55e";
    }

    // Update text
    scoreNumber.innerText = score;
    scoreStatus.innerText = statusText;
    
    // Reset status classes
    scoreStatus.className = "score-status " + statusClass;

    // Animate the SVG circular ring
    // Circumference = 2 * PI * r = 2 * 3.14159 * 15.9155 = 100
    // So stroke-dasharray "score, 100" fills it perfectly!
    scoreCircle.style.strokeDasharray = `${score}, 100`;
    scoreCircle.style.stroke = color;
}

/* ───────────────────────────────────── */
/* TELEMETRY SIMULATOR TRIGGER */
/* ───────────────────────────────────── */

async function triggerSimulation() {
    const profileJson = localStorage.getItem("patientProfile");
    if (!profileJson) {
        alert("Please register patient details first.");
        return;
    }

    let profile = JSON.parse(profileJson);
    const btn = document.getElementById("btnSimulate");

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation: spin 1s linear infinite;"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
            Simulating Telemetry...
        `;
    }

    try {
        const response = await fetch('/api/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ patient_id: profile.patient_id })
        });

        if (!response.ok) {
            throw new Error("Simulation endpoint failed.");
        }

        const data = await response.json();
        console.log("Simulated telemetry registered successfully:", data);

        // Instantly reload dashboard to reflect newly stored DB values
        await updateDashboard();

    } catch (error) {
        console.error("PPG simulation failed:", error);
        alert("Simulation Error: " + error.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation: pulse 1.2s infinite;"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                Simulate PPG Sensor
            `;
        }
    }
}

/* ───────────────────────────────────── */
/* SIDEBAR NAVIGATION (SPA VIEW TRANSITION) */
/* ───────────────────────────────────── */

function switchView(viewName) {
    const menuItems = {
        'dashboard': 'sidebarDashboard',
        'patientInfo': 'sidebarPatientInfo',
        'reports': 'sidebarReports',
        'registerNew': 'sidebarRegisterNew'
    };

    // Remove active styles from sidebar nodes
    Object.values(menuItems).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove("active");
    });

    // Add active style to selected node
    const activeEl = document.getElementById(menuItems[viewName]);
    if (activeEl) activeEl.classList.add("active");

    const dashboardSec = document.getElementById("dashboardSection");
    const patientInfoSec = document.getElementById("patientInfoSection");
    const reportsSec = document.getElementById("reportsSection");

    // Perform view operations
    if (viewName === 'dashboard') {
        if (dashboardSec) dashboardSec.classList.remove("hidden-view");
        if (patientInfoSec) patientInfoSec.classList.add("hidden-view");
        if (reportsSec) reportsSec.classList.add("hidden-view");
        updateDashboard();
    } else if (viewName === 'patientInfo') {
        if (dashboardSec) dashboardSec.classList.add("hidden-view");
        if (patientInfoSec) patientInfoSec.classList.remove("hidden-view");
        if (reportsSec) reportsSec.classList.add("hidden-view");
        loadPatientInfoAndStats();
    } else if (viewName === 'reports') {
        if (dashboardSec) dashboardSec.classList.add("hidden-view");
        if (patientInfoSec) patientInfoSec.classList.add("hidden-view");
        if (reportsSec) reportsSec.classList.remove("hidden-view");
        loadPatientReportData();
    } else if (viewName === 'registerNew') {
        if (confirm("Are you sure you want to register a new patient? This will clear the form values and reset the active patient profile session.")) {
            // clear profile from localStorage
            localStorage.removeItem("patientProfile");
            
            // reset form inputs
            const nameInput = document.getElementById("inputName");
            const ageInput = document.getElementById("inputAge");
            const weightInput = document.getElementById("inputWeight");
            const genderInput = document.getElementById("inputGender");
            if (nameInput) nameInput.value = "";
            if (ageInput) ageInput.value = "";
            if (weightInput) weightInput.value = "";
            if (genderInput) genderInput.value = "";
            
            // transition to form view (1st page)
            const formView = document.getElementById("formView");
            const dashboardView = document.getElementById("dashboardView");
            if (formView) {
                formView.classList.remove("hidden-view");
                formView.classList.remove("fade-out"); // remove fade-out if it exists from previous transitions
            }
            if (dashboardView) {
                dashboardView.classList.add("hidden-view");
            }
            
            // reset active navigation styles so next time we go to dashboard/profile it shows correctly
            if (activeEl) activeEl.classList.remove("active");
            const dashSidebar = document.getElementById("sidebarDashboard");
            if (dashSidebar) dashSidebar.classList.add("active");
        } else {
            // Revert back to the active view (patientInfo or dashboard)
            const currentActive = (patientInfoSec && !patientInfoSec.classList.contains("hidden-view")) ? 'patientInfo' : 'dashboard';
            setTimeout(() => switchView(currentActive), 200);
        }
    }
}

/* ───────────────────────────────────── */
/* CLINICAL REPORTS VIEW DATA POPULATOR */
/* ───────────────────────────────────── */

async function loadPatientReportData() {
    const profileJson = localStorage.getItem("patientProfile");
    if (!profileJson) {
        showRegistrationForm();
        return;
    }

    let profile;
    try {
        profile = JSON.parse(profileJson);
    } catch (e) {
        showRegistrationForm();
        return;
    }

    // Set today's date in report
    const reportDateEl = document.getElementById("reportDate");
    if (reportDateEl) {
        const today = new Date();
        reportDateEl.innerText = `Date: ${today.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}`;
    }

    try {
        // Fetch patient demographics and stats from server
        const response = await fetch(`/api/patients/${profile.patient_id}`);
        if (!response.ok) throw new Error("Failed to load patient insights and stats");
        const data = await response.json();

        // Update database label if returned
        if (data.db_type) {
            updateDbStatus(data.db_type);
        }

        // Fill Demographic data
        const repName = document.getElementById("repName");
        const repID = document.getElementById("repID");
        const repAgeGender = document.getElementById("repAgeGender");
        const repWeight = document.getElementById("repWeight");
        const repBloodGroup = document.getElementById("repBloodGroup");
        const repRegDate = document.getElementById("repRegDate");

        if (repName) repName.innerText = data.name;
        if (repID) repID.innerText = data.patient_id;
        if (repAgeGender) repAgeGender.innerText = `${data.age} Years / ${data.gender}`;
        if (repWeight) repWeight.innerText = `${data.weight} KG`;
        if (repBloodGroup) {
            repBloodGroup.innerText = data.blood_group;
        }
        if (repRegDate) repRegDate.innerText = data.created_at || "Not Available";

        // Fill Stats
        const stats = data.stats || {};
        const repTotalReadings = document.getElementById("repTotalReadings");
        const repAvgGlucose = document.getElementById("repAvgGlucose");
        const repGlucoseRange = document.getElementById("repGlucoseRange");
        const repAvgHeartRate = document.getElementById("repAvgHeartRate");

        if (repTotalReadings) repTotalReadings.innerText = stats.total_readings !== undefined ? stats.total_readings : 0;
        if (repAvgGlucose) repAvgGlucose.innerText = stats.avg_glucose ? `${parseFloat(stats.avg_glucose).toFixed(1)} mg/dL` : "0.0 mg/dL";
        if (repGlucoseRange) {
            if (stats.total_readings > 0) {
                repGlucoseRange.innerText = `${parseFloat(stats.min_glucose).toFixed(1)} - ${parseFloat(stats.max_glucose).toFixed(1)} mg/dL`;
            } else {
                repGlucoseRange.innerText = "0 - 0 mg/dL";
            }
        }
        if (repAvgHeartRate) repAvgHeartRate.innerText = stats.avg_heart_rate ? `${parseFloat(stats.avg_heart_rate).toFixed(1)} BPM` : "0.0 BPM";

        // Fetch and draw history table for Patient Report view
        const historyResponse = await fetch(`/api/history/${profile.patient_id}`);
        if (historyResponse.ok) {
            const histData = await historyResponse.json();
            renderReportHistoryTable(histData.history || []);
        }

    } catch (error) {
        console.error("Patient report retrieval failed:", error);
    }
}

function renderReportHistoryTable(history) {
    const tbody = document.getElementById("repHistoryBody");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (history.length === 0) {
        const row = tbody.insertRow();
        const cell = row.insertCell(0);
        cell.colSpan = 5;
        cell.innerHTML = "<em style='color: #64748b;'>No telemetry logs found in database.</em>";
        cell.style.padding = "20px";
        cell.style.textAlign = "center";
        return;
    }

    history.forEach(item => {
        const row = tbody.insertRow();
        
        const c0 = row.insertCell(0);
        c0.innerHTML = item.time;
        c0.style.padding = "10px";
        c0.style.borderBottom = "1px solid #cbd5e1";

        const c1 = row.insertCell(1);
        c1.innerHTML = `<strong>${parseFloat(item.glucose).toFixed(1)} mg/dL</strong>`;
        c1.style.padding = "10px";
        c1.style.borderBottom = "1px solid #cbd5e1";
        
        let catColor = "#22c55e"; // green
        const cat = item.category.toLowerCase();
        if (cat.includes("high")) catColor = "#ef4444"; // red
        else if (cat.includes("pre-diabetic")) catColor = "#f59e0b"; // yellow
        else if (cat.includes("low")) catColor = "#0077b6"; // blue
        
        const c2 = row.insertCell(2);
        c2.innerHTML = `<span style="color: ${catColor}; font-weight: 600;">${item.category}</span>`;
        c2.style.padding = "10px";
        c2.style.borderBottom = "1px solid #cbd5e1";

        const c3 = row.insertCell(3);
        c3.innerHTML = `${parseFloat(item.heart_rate).toFixed(1)} BPM`;
        c3.style.padding = "10px";
        c3.style.borderBottom = "1px solid #cbd5e1";

        const c4 = row.insertCell(4);
        c4.innerHTML = `${item.confidence}%`;
        c4.style.padding = "10px";
        c4.style.borderBottom = "1px solid #cbd5e1";
    });
}

/* ───────────────────────────────────── */
/* HIGH-FIDELITY CLIENT-SIDE PDF EXPORT  */
/* ───────────────────────────────────── */

function downloadClinicalReportPDF() {
    const profileJson = localStorage.getItem("patientProfile");
    if (!profileJson) {
        alert("Please register patient details first.");
        return;
    }
    
    let profile;
    try {
        profile = JSON.parse(profileJson);
    } catch (e) {
        return;
    }
    
    const element = document.getElementById("clinicalReportSheet");
    const btn = document.getElementById("btnDownloadPDF");
    
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `
            <svg class="spin-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation: spin 1s linear infinite;"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
            Generating PDF...
        `;
    }
    
    const opt = {
        margin:       10,
        filename:     `BioScan_Clinical_Report_${profile.name.replace(/\s+/g, '_')}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { scale: 2.5, useCORS: true, letterRendering: true },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak:    { mode: ['css', 'legacy'], avoid: ['tr', 'td', 'th', '.avoid-break'] }
    };
    
    html2pdf().set(opt).from(element).save().then(() => {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                Export Official PDF Report
            `;
        }
    }).catch(err => {
        console.error("PDF generation failed:", err);
        alert("Error exporting PDF: " + err.message);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                Export Official PDF Report
            `;
        }
    });
}

/* ───────────────────────────────────── */
/* PATIENT INFO VIEW STATS & HISTORY FETCH */
/* ───────────────────────────────────── */

async function loadPatientInfoAndStats() {
    const profileJson = localStorage.getItem("patientProfile");
    if (!profileJson) {
        showRegistrationForm();
        return;
    }

    let profile;
    try {
        profile = JSON.parse(profileJson);
    } catch (e) {
        showRegistrationForm();
        return;
    }

    try {
        const response = await fetch(`/api/patients/${profile.patient_id}`);
        if (!response.ok) throw new Error("Failed to load patient insights and stats");
        const data = await response.json();

        // Update database label if returned
        if (data.db_type) {
            updateDbStatus(data.db_type);
        }

        // Update profile elements on the profile card (left column)
        const infoName = document.getElementById("infoName");
        const infoPatientID = document.getElementById("infoPatientID");
        const infoAge = document.getElementById("infoAge");
        const infoWeight = document.getElementById("infoWeight");
        const infoGender = document.getElementById("infoGender");
        const infoBloodGroup = document.getElementById("infoBloodGroup");
        const infoRegDate = document.getElementById("infoRegDate");
        const infoAvatar = document.getElementById("infoAvatar");

        if (infoName) infoName.innerText = data.name;
        if (infoPatientID) infoPatientID.innerText = `ID: ${data.patient_id}`;
        if (infoAge) infoAge.innerText = `${data.age} Years`;
        if (infoWeight) infoWeight.innerText = `${data.weight} KG`;
        if (infoGender) infoGender.innerText = data.gender;
        if (infoBloodGroup) {
            infoBloodGroup.innerText = data.blood_group;
        }
        if (infoRegDate) infoRegDate.innerText = data.created_at || "Not Available";
        if (infoAvatar && data.name) {
            infoAvatar.innerText = data.name.trim().charAt(0).toUpperCase();
        }

        // Update stats (right column cards)
        const stats = data.stats || {};
        const statTotal = document.getElementById("statTotalReadings");
        const statAvgGlucose = document.getElementById("statAvgGlucose");
        const statGlucoseRange = document.getElementById("statGlucoseRange");
        const statAvgHeartRate = document.getElementById("statAvgHeartRate");

        if (statTotal) statTotal.innerText = stats.total_readings !== undefined ? stats.total_readings : 0;
        if (statAvgGlucose) statAvgGlucose.innerText = stats.avg_glucose ? `${parseFloat(stats.avg_glucose).toFixed(1)}` : "0.0";
        if (statGlucoseRange) {
            if (stats.total_readings > 0) {
                statGlucoseRange.innerText = `${parseFloat(stats.min_glucose).toFixed(1)} - ${parseFloat(stats.max_glucose).toFixed(1)}`;
            } else {
                statGlucoseRange.innerText = "0 - 0";
            }
        }
        if (statAvgHeartRate) statAvgHeartRate.innerText = stats.avg_heart_rate ? `${parseFloat(stats.avg_heart_rate).toFixed(1)}` : "0.0";

        // Fetch and draw history table for Patient Info view
        const historyResponse = await fetch(`/api/history/${profile.patient_id}`);
        if (historyResponse.ok) {
            const histData = await historyResponse.json();
            renderPatientInfoHistoryTable(histData.history || []);
        }

    } catch (error) {
        console.error("Patient insights retrieval failed:", error);
    }
}

function renderPatientInfoHistoryTable(history) {
    const tbody = document.getElementById("infoHistoryBody");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (history.length === 0) {
        const row = tbody.insertRow();
        const cell = row.insertCell(0);
        cell.colSpan = 5;
        cell.innerHTML = "<em style='color: #64748b;'>No telemetry logs found in database. Please connect IoT device to start recording.</em>";
        cell.style.padding = "20px";
        return;
    }

    history.forEach(item => {
        const row = tbody.insertRow();
        
        row.insertCell(0).innerHTML = item.time;
        row.insertCell(1).innerHTML = `<strong>${parseFloat(item.glucose).toFixed(1)}</strong>`;
        
        let catClass = "normal";
        const cat = item.category.toLowerCase();
        if (cat.includes("high")) catClass = "high";
        else if (cat.includes("pre-diabetic")) catClass = "pre-diabetic";
        
        row.insertCell(2).innerHTML = `<span class="badge ${catClass}" style="margin-top:0; padding:4px 12px; font-size:12px;">${item.category}</span>`;
        row.insertCell(3).innerHTML = `${parseFloat(item.heart_rate).toFixed(1)} BPM`;
        row.insertCell(4).innerHTML = `${item.confidence}%`;
    });
}

// Inline CSS for spin keyframes if not defined
const style = document.createElement('style');
style.innerHTML = `
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
`;
document.head.appendChild(style);


/* ───────────────────────────────────── */
/* LIVE CLOCK */
/* ───────────────────────────────────── */

function updateClock(){
    const clockTextEl = document.getElementById("liveClock");
    if(clockTextEl) {
        const now = new Date();
        clockTextEl.innerHTML = `Live Monitoring • ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
    }
}

/* ───────────────────────────────────── */
/* START EVERYTHING */
/* ───────────────────────────────────── */

updateClock();

// Set interval routines
setInterval(updateDashboard, 3000); // Polling every 3 seconds for new readings
setInterval(updateClock, 1000);