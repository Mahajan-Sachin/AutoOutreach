const API_BASE = (window.location.origin.includes("http") && !window.location.origin.includes("null")) ? `${window.location.origin}/api` : "http://4.145.88.53:8000/api";

let currentPendingDrafts = [];
let activeReviewDraft = null;

function getAuthToken() {
    return localStorage.getItem("jobfit_auth_token");
}

function showLoginModal() {
    const modal = document.getElementById("auth-modal");
    if (modal) modal.style.display = "flex";
}

function hideLoginModal() {
    const modal = document.getElementById("auth-modal");
    if (modal) modal.style.display = "none";
}

async function verifyAuthSession() {
    const token = getAuthToken();
    if (!token) {
        showLoginModal();
        return false;
    }
    try {
        const res = await fetch(`${API_BASE}/auth/verify`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (res.ok) {
            const data = await res.json();
            const username = data?.user?.sub || "sachin";
            const sessionNameEl = document.getElementById("session-username");
            if (sessionNameEl) sessionNameEl.textContent = username;
            hideLoginModal();
            return true;
        } else {
            localStorage.removeItem("jobfit_auth_token");
            showLoginModal();
            return false;
        }
    } catch (e) {
        console.warn("[Auth Verify Error]:", e);
        showLoginModal();
        return false;
    }
}

async function authFetch(url, options = {}) {
    let token = getAuthToken();
    if (!token) {
        showLoginModal();
        throw new Error("Unauthorized: Please sign in first.");
    }
    options.headers = options.headers || {};
    options.headers["Authorization"] = `Bearer ${token}`;
    
    let res = await fetch(url, options);
    if (res.status === 401) {
        localStorage.removeItem("jobfit_auth_token");
        showLoginModal();
        throw new Error("Session expired. Please sign in again.");
    }
    return res;
}

document.addEventListener("DOMContentLoaded", async () => {
    initNavigation();
    initEventListeners();
    initAuthListeners();
    initCsvEnrichListeners();
    
    const isAuthenticated = await verifyAuthSession();
    if (isAuthenticated) {
        loadDashboardMetrics();
        loadPendingQueue();
        loadHistory();
        discoverStartups();
    }
});


function initAuthListeners() {
    const loginForm = document.getElementById("auth-login-form");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const usernameInput = document.getElementById("auth-username-input");
            const passwordInput = document.getElementById("auth-password-input");
            const errorMsgEl = document.getElementById("auth-error-msg");
            const submitBtn = document.getElementById("btn-auth-submit");

            const username = usernameInput.value.trim();
            const password = passwordInput.value.trim();

            if (!username || !password) return;

            submitBtn.disabled = true;
            submitBtn.textContent = "Verifying...";
            errorMsgEl.style.display = "none";

            try {
                const res = await fetch(`${API_BASE}/auth/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });

                if (res.ok) {
                    const data = await res.json();
                    localStorage.setItem("jobfit_auth_token", data.access_token);
                    const sessionNameEl = document.getElementById("session-username");
                    if (sessionNameEl) sessionNameEl.textContent = username;
                    
                    hideLoginModal();
                    passwordInput.value = "";
                    
                    loadDashboardMetrics();
                    loadPendingQueue();
                    loadHistory();
                    discoverStartups();
                } else {
                    errorMsgEl.textContent = "Invalid username or password. Access denied.";
                    errorMsgEl.style.display = "block";
                }
            } catch (err) {
                errorMsgEl.textContent = "Connection error. Is backend online?";
                errorMsgEl.style.display = "block";
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = "<span>Sign In to Dashboard</span>";
            }
        });
    }

    const logoutBtn = document.getElementById("btn-logout");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            localStorage.removeItem("jobfit_auth_token");
            showLoginModal();
        });
    }
}

function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach(item => {
        item.addEventListener("click", () => {
            navItems.forEach(n => n.classList.remove("active"));
            item.classList.add("active");

            const tab = item.dataset.tab;
            document.querySelectorAll(".tab-view").forEach(view => {
                view.classList.remove("active");
            });
            document.getElementById(`view-${tab}`).classList.add("active");

            // Update page header
            if (tab === "discover") {
                document.getElementById("page-title").textContent = "Global Tech Startup Discovery";
                document.getElementById("page-subtitle").textContent = "Autonomous multi-region search & $0 credit deduplication pipeline";
            } else if (tab === "role-search") {
                document.getElementById("page-title").textContent = "Desired Role Search & Fit Match";
                document.getElementById("page-subtitle").textContent = "Search active job postings across ATS portals with AI fit scoring";
            } else if (tab === "autofill") {
                document.getElementById("page-title").textContent = "Career Site Form Auto-Filler";
                document.getElementById("page-subtitle").textContent = "Auto-fill Greenhouse, Lever, and Ashby job applications with AI custom essay answers";
            } else if (tab === "csv-enrich") {
                document.getElementById("page-title").textContent = "Batch CSV Lead & Email Enrichment";
                document.getElementById("page-subtitle").textContent = "Auto-detect organizations, query Hunter.io & Apollo, and export enriched CSVs";
            } else if (tab === "pending") {
                document.getElementById("page-title").textContent = "HITL Approval Queue";
                document.getElementById("page-subtitle").textContent = "Review tailored pitch emails before sending";
                loadPendingQueue();
            } else if (tab === "history") {
                document.getElementById("page-title").textContent = "Outreach History";
                document.getElementById("page-subtitle").textContent = "Processed companies, cache hits, and sent emails";
                loadHistory();
            }
        });
    });
}

function initEventListeners() {
    // Discover Startups button
    document.getElementById("btn-discover").addEventListener("click", discoverStartups);

    // Nightly Scan button
    document.getElementById("btn-nightly-scan").addEventListener("click", triggerNightlyScan);

    // Role Search button
    document.getElementById("btn-run-role-search").addEventListener("click", runRoleSearch);

    // Autofill button
    document.getElementById("btn-run-autofill").addEventListener("click", runAutofill);

    // Manual domain outreach button
    document.getElementById("btn-manual-outreach").addEventListener("click", () => {
        const input = document.getElementById("manual-domain-input");
        const domain = input.value.trim();
        if (domain) {
            triggerOutreachForDomain(domain);
            input.value = "";
        }
    });

    // Modal close & approval buttons
    document.getElementById("modal-close-btn").addEventListener("click", closeModal);
    document.getElementById("modal-reject-btn").addEventListener("click", rejectActivePitch);
    document.getElementById("modal-approve-gmail-btn").addEventListener("click", approveActivePitch);
}

let currentDiscoveredRegions = { us_yc: [], eu: [], asia_me: [] };
let activeRegionTab = "us_yc";

async function discoverStartups() {
    const btn = document.getElementById("btn-discover");
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">🌀</span> Searching US/EU/Asia...`;

    const container = document.getElementById("startups-container");
    container.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">🌐</div>
            <h3>Discovering Fresh Tech Startups...</h3>
            <p>Running low-credit Tavily US/YC search + free DDG Europe & Asia nodes.</p>
        </div>
    `;

    try {
        const res = await authFetch(`${API_BASE}/discover`);
        const data = await res.json();
        currentDiscoveredRegions = data.regions || { us_yc: [], eu: [], asia_me: [] };
        document.getElementById("metric-discovered").textContent = data.total || 0;
        initRegionTabListeners();
        renderStartupsForActiveRegion();
    } catch (err) {
        console.error("Discovery error:", err);
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <h3>Failed to connect to LangGraph Backend</h3>
                <p>Ensure FastAPI server is running on http://localhost:8000</p>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-icon">🚀</span> <span>Discover Fresh Startups</span>`;
    }
}

function initRegionTabListeners() {
    const tabs = document.querySelectorAll(".region-tab");
    tabs.forEach(tab => {
        tab.onclick = () => {
            tabs.forEach(t => {
                t.style.background = "rgba(255,255,255,0.05)";
                t.style.color = "var(--text-muted)";
                t.style.borderColor = "rgba(255,255,255,0.1)";
            });
            tab.style.background = "rgba(0,240,255,0.15)";
            tab.style.color = "var(--primary-cyan)";
            tab.style.borderColor = "rgba(0,240,255,0.3)";
            activeRegionTab = tab.dataset.region;
            renderStartupsForActiveRegion();
        };
    });
}

function renderStartupsForActiveRegion() {
    const container = document.getElementById("startups-container");
    const startups = currentDiscoveredRegions[activeRegionTab] || [];

    if (startups.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🔍</div>
                <h3>No Startups Found in This Region</h3>
                <p>Click "Discover Fresh Startups" above to pull latest companies.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = startups.map(s => `
        <div class="startup-card">
            <div class="card-top">
                <div>
                    <h4 class="company-title">${escapeHtml(s.name)}</h4>
                    <span class="company-domain">${escapeHtml(s.domain)}</span>
                </div>
                <div style="display:flex; gap:6px; flex-direction:column; align-items:flex-end;">
                    <span class="badge" style="background:rgba(112,0,255,0.2); color:#b57cff; border-color:rgba(112,0,255,0.4); font-size:10px">${escapeHtml(s.source || 'Search')}</span>
                    ${s.is_cached ? `<span class="badge" style="color:#00ff88; border-color:rgba(0,255,136,0.3); font-size:10px">Cached</span>` : `<span class="badge" style="font-size:10px">Fresh</span>`}
                </div>
            </div>
            <p class="card-snippet">${escapeHtml(s.snippet || "Tech startup operating in software & AI domain.")}</p>
            <div class="card-footer" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="display:flex; gap:10px; font-size:12px;">
                    <a href="${s.url}" target="_blank" style="color:var(--text-muted); text-decoration:none">Website ↗</a>
                    <a href="${s.linkedin_url}" target="_blank" style="color:var(--primary-cyan); text-decoration:none">LinkedIn 💼</a>
                    <a href="${s.careers_url}" target="_blank" style="color:#b57cff; text-decoration:none">Careers 🚀</a>
                </div>
                <button class="btn btn-secondary" onclick="triggerOutreachForDomain('${s.domain}')" ${s.is_cached ? 'disabled' : ''}>
                    ${s.is_cached ? 'Already Scanned' : 'Run Outreach ⚡'}
                </button>
            </div>
        </div>
    `).join("");
}

async function triggerOutreachForDomain(domain) {
    alert(`⚡ Starting LangGraph Agent Outreach Pipeline for: ${domain}`);
    try {
        const res = await authFetch(`${API_BASE}/outreach`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain: domain })
        });
        const data = await res.json();
        
        if (data.status === "CACHED") {
            alert(`ℹ️ Cache Hit! ${domain} was already scanned previously. $0 credits spent.`);
        } else {
            alert(`✅ Outreach Pipeline Complete! Draft pitches created for ${domain}.`);
            loadPendingQueue();
        }
    } catch (err) {
        console.error("Outreach trigger error:", err);
        alert("⚠️ Backend server error. Make sure FastAPI is running on port 8000.");
    }
}

async function loadPendingQueue() {
    try {
        const res = await authFetch(`${API_BASE}/pending`);
        const data = await res.json();
        currentPendingDrafts = data.pending_drafts || [];

        // Update counts
        document.getElementById("pending-count").textContent = currentPendingDrafts.length;
        document.getElementById("metric-pending").textContent = currentPendingDrafts.length;

        renderPendingList(currentPendingDrafts);
    } catch (err) {
        console.error("Pending queue load error:", err);
    }
}

function formatTimestamp(dateStr) {
    if (!dateStr) return "";
    try {
        // Handle SQLite UTC timestamp format YYYY-MM-DD HH:MM:SS
        const utcString = dateStr.includes("Z") || dateStr.includes("+") ? dateStr : dateStr.replace(" ", "T") + "Z";
        const date = new Date(utcString);
        if (isNaN(date.getTime())) return dateStr;
        
        const now = new Date();
        const isToday = date.toDateString() === now.toDateString();
        const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
        
        return isToday ? `Today at ${timeStr}` : `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })} at ${timeStr}`;
    } catch(e) {
        return dateStr;
    }
}

function renderPendingList(drafts) {
    const container = document.getElementById("pending-container");
    if (drafts.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">✅</div>
                <h3>No Pending Approvals</h3>
                <p>Your outreach queue is clear! Discover startups to generate new tailored emails.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = drafts.map(d => `
        <div class="pending-card">
            <div class="pending-info">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; gap:8px;">
                    <h4 style="margin:0">${escapeHtml(d.company_name)} (${escapeHtml(d.company_domain)})</h4>
                    <span class="badge" style="background:rgba(255,255,255,0.06); color:var(--text-muted); border-color:rgba(255,255,255,0.1); font-size:11px; white-space:nowrap; flex-shrink:0;">🕒 ${escapeHtml(formatTimestamp(d.created_at))}</span>
                </div>
                <p class="pending-meta" style="display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:4px;">
                    <span>Target: <strong style="color:var(--primary-cyan)">${d.role_target} Pitch</strong> • 
                    Recipient: ${escapeHtml(d.contact_name || 'Executive')} (${escapeHtml(d.contact_email || 'founders@domain')})</span>
                    <span class="badge" style="background:rgba(181, 124, 255, 0.15); color:#b57cff; border:1px solid rgba(181, 124, 255, 0.35); font-size:10px; font-weight:600; padding:2px 8px; border-radius:12px; white-space:nowrap;">
                        🔍 Source: ${escapeHtml(d.contact_email_source || 'AI Discovery')}
                    </span>
                </p>
                <p style="font-size:13px; color:var(--text-muted); margin-top:6px">Subject: ${escapeHtml(d.pitch_subject)}</p>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
                <button class="btn btn-secondary" onclick="openReviewModal(${d.draft_id})">Review & Edit ✏️</button>
                <button class="btn" style="background:rgba(255,68,68,0.15); color:#ff4444; border:1px solid rgba(255,68,68,0.3); padding:8px 12px; font-size:12px; border-radius:6px; cursor:pointer;" onclick="deleteDraft(${d.draft_id})" title="Delete Draft">🗑️ Delete</button>
            </div>
        </div>
    `).join("");
}

function openReviewModal(draftId) {
    const draft = currentPendingDrafts.find(d => d.draft_id === draftId);
    if (!draft) return;

    activeReviewDraft = draft;

    document.getElementById("modal-company-name").textContent = `${draft.company_name} (${draft.company_domain})`;
    document.getElementById("modal-role-target").textContent = `${draft.role_target} Pitch`;
    document.getElementById("modal-contact-info").value = `${draft.contact_name || 'Executive'} (${draft.contact_email || 'founders@domain'})`;
    document.getElementById("modal-subject-input").value = draft.pitch_subject;
    document.getElementById("modal-body-input").value = draft.pitch_body;

    // Set Gmail compose link
    document.getElementById("modal-approve-gmail-btn").href = draft.gmail_compose_url;

    document.getElementById("review-modal").classList.add("active");
}

function closeModal() {
    document.getElementById("review-modal").classList.remove("active");
    activeReviewDraft = null;
}

async function approveActivePitch() {
    if (!activeReviewDraft) return;
    try {
        await authFetch(`${API_BASE}/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ draft_id: activeReviewDraft.draft_id, action: "approve" })
        });
        closeModal();
        loadPendingQueue();
        loadHistory();
        
        // Update metric
        const sentEl = document.getElementById("metric-sent");
        sentEl.textContent = parseInt(sentEl.textContent || 0) + 1;
    } catch (err) {
        console.error("Approve error:", err);
    }
}

async function rejectActivePitch() {
    if (!activeReviewDraft) return;
    try {
        await authFetch(`${API_BASE}/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ draft_id: activeReviewDraft.draft_id, action: "reject" })
        });
        closeModal();
        loadPendingQueue();
    } catch (err) {
        console.error("Reject error:", err);
    }
}

async function deleteActivePitch() {
    if (!activeReviewDraft) return;
    await deleteDraft(activeReviewDraft.draft_id);
}

async function deleteDraft(draftId) {
    try {
        await authFetch(`${API_BASE}/draft/${draftId}`, { method: "DELETE" });
        if (activeReviewDraft && activeReviewDraft.draft_id === draftId) {
            closeModal();
        }
        loadPendingQueue();
        loadHistory();
    } catch (err) {
        console.error("Delete error:", err);
    }
}

async function loadHistory() {
    try {
        const res = await authFetch(`${API_BASE}/history`);
        const data = await res.json();
        const history = data.history || [];

        const tbody = document.getElementById("history-table-body");
        if (history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted)">No outreach history recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = history.map(h => `
            <tr>
                <td><strong>${escapeHtml(h.company_name)}</strong> <br><small style="color:var(--text-muted)">${escapeHtml(h.company_domain)}</small></td>
                <td>${escapeHtml(h.contact_name || 'Executive')}<br><small style="color:var(--primary-cyan)">${escapeHtml(h.contact_email || '-')}</small></td>
                <td><span class="badge">${h.role_target}</span></td>
                <td><span style="color:${h.status === 'APPROVED' ? 'var(--green-accent)' : 'var(--orange-accent)'}">${h.status}</span></td>
                <td style="font-size:12px; color:var(--text-muted)">${h.sent_at ? formatTimestamp(h.sent_at) : 'Pending'}</td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("History load error:", err);
    }
}

async function triggerNightlyScan() {
    const btn = document.getElementById("btn-nightly-scan");
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">🌀</span> Running Scan...`;
    try {
        const res = await authFetch(`${API_BASE}/nightly-scan`, { method: "POST" });
        const data = await res.json();
        alert("🌙 Nightly Scan Started! The system is discovering startups, scanning active role postings, and generating pitches in the background.");
    } catch (err) {
        alert("Scan trigger error: " + err);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span class="btn-icon">🌙</span> Nightly Scan`;
    }
}

async function runRoleSearch() {
    const input = document.getElementById("role-search-input");
    const query = input.value.trim();
    const container = document.getElementById("role-jobs-container");
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">🌀</div><h3>Searching ATS Portals...</h3><p>Scanning Greenhouse, Lever, and Ashby for "${query || 'AI Engineer'}"...</p></div>`;

    try {
        const res = await authFetch(`${API_BASE}/role-search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role_query: query, limit: 10 })
        });
        const data = await res.json();
        const jobs = data.jobs || [];

        if (jobs.length === 0) {
            container.innerHTML = `<div class="empty-state"><div class="empty-icon">🔍</div><h3>No Job Matches Found</h3><p>Try searching for a different role query.</p></div>`;
            return;
        }

        container.innerHTML = jobs.map(j => `
            <div class="startup-card" style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:16px; display:flex; flex-direction:column; justify-content:space-between;">
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="badge" style="background:rgba(0,240,255,0.15); color:var(--primary-cyan);">${j.fit_score}% Fit Match</span>
                        <span class="badge" style="background:rgba(255,255,255,0.05); color:var(--text-muted);">${j.portal_type.toUpperCase()}</span>
                    </div>
                    <h4 style="margin:10px 0 4px 0; color:#fff;">${escapeHtml(j.title)}</h4>
                    <p style="margin:0 0 10px 0; font-size:13px; color:var(--primary-cyan); font-weight:600;">${escapeHtml(j.company)}</p>
                    <p style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">${escapeHtml(j.snippet)}</p>
                    <div style="margin-bottom:10px;">
                        ${(j.strengths || []).map(s => `<span style="font-size:11px; display:inline-block; background:rgba(0,255,136,0.1); color:#00ff88; padding:3px 8px; border-radius:4px; margin:2px;">✓ ${escapeHtml(s)}</span>`).join("")}
                    </div>
                </div>
                <div style="display:flex; gap:8px; margin-top:10px;">
                    <a href="${j.url}" target="_blank" class="btn" style="flex:1; text-align:center; background:rgba(255,255,255,0.05); color:#fff; border:1px solid rgba(255,255,255,0.1); padding:8px; border-radius:6px; font-size:12px; text-decoration:none;">View Job Listing ↗</a>
                    <button class="btn btn-primary" onclick="quickAutofill('${j.url}')" style="padding:8px 12px; font-size:12px;">⚡ Auto-Fill</button>
                </div>
            </div>
        `).join("");
    } catch (err) {
        container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><h3>Role Search Error</h3><p>${err}</p></div>`;
    }
}

async function quickAutofill(url) {
    document.querySelector("[data-tab='autofill']").click();
    document.getElementById("autofill-url-input").value = url;
    runAutofill();
}

async function runAutofill() {
    const input = document.getElementById("autofill-url-input");
    const url = input.value.trim();
    if (!url) return alert("Please enter a job application URL!");

    const statusBox = document.getElementById("autofill-status-box");
    const statusTitle = document.getElementById("autofill-status-title");
    const statusDesc = document.getElementById("autofill-status-desc");

    statusBox.style.display = "block";
    statusTitle.style.color = "var(--primary-cyan)";
    statusTitle.textContent = "⚡ Playwright Engine Launching...";
    statusDesc.textContent = `Inspecting DOM and preparing autofill fields for ${url}...`;

    try {
        const res = await fetch(`${API_BASE}/autofill`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: url, submit_live: false })
        });
        const result = await res.json();

        if (result.status === "PREFILLED" || result.status === "SUBMITTED") {
            statusTitle.style.color = "#00ff88";
            statusTitle.textContent = `✅ ${result.status} (${result.portal_detected})`;
            statusDesc.textContent = result.message;
        } else {
            statusTitle.style.color = "#ff4444";
            statusTitle.textContent = `⚠️ Autofill Alert (${result.portal_detected})`;
            statusDesc.textContent = result.message || "Failed to parse or populate form fields.";
        }
    } catch (err) {
        statusTitle.style.color = "#ff4444";
        statusTitle.textContent = "⚠️ Request Error";
        statusDesc.textContent = err.toString();
    }
}

async function uploadResumePDF(inputElement) {
    const file = inputElement.files[0];
    if (!file) return;

    const statusBox = document.getElementById("resume-upload-status");
    statusBox.style.display = "block";
    statusBox.style.background = "rgba(0, 240, 255, 0.1)";
    statusBox.style.color = "#00f0ff";
    statusBox.style.border = "1px solid rgba(0, 240, 255, 0.3)";
    statusBox.textContent = `⏳ Uploading and parsing ${file.name} with Groq AI...`;

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch(`${API_BASE}/upload-resume`, {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        if (res.ok) {
            statusBox.style.background = "rgba(0, 255, 136, 0.1)";
            statusBox.style.color = "#00ff88";
            statusBox.style.border = "1px solid rgba(0, 255, 136, 0.3)";
            statusBox.textContent = `✅ ${data.message} Master profile updated for ${data.profile.first_name} ${data.profile.last_name}!`;
        } else {
            throw new Error(data.detail || "Failed to parse resume PDF.");
        }
    } catch (err) {
        console.error("Resume upload error:", err);
        statusBox.style.background = "rgba(255, 68, 68, 0.1)";
        statusBox.style.color = "#ff4444";
        statusBox.style.border = "1px solid rgba(255, 68, 68, 0.3)";
        statusBox.textContent = `⚠️ Upload Error: ${err.message}`;
    }
}

function loadDashboardMetrics() {
    loadPendingQueue();
    loadHistory();
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

let currentEnrichedDownloadId = null;

function initCsvEnrichListeners() {
    const dropzone = document.getElementById("csv-dropzone");
    const fileInput = document.getElementById("csv-file-input");
    const demoBtn = document.getElementById("btn-load-sample-csv");
    const downloadBtn = document.getElementById("btn-download-enriched-csv");

    if (dropzone && fileInput) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => {
                dropzone.style.borderColor = "var(--primary-cyan)";
                dropzone.style.background = "rgba(0, 240, 255, 0.08)";
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => {
                dropzone.style.borderColor = "rgba(0, 240, 255, 0.35)";
                dropzone.style.background = "rgba(255, 255, 255, 0.03)";
            }, false);
        });

        dropzone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                processCsvFile(files[0]);
            }
        });

        fileInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files.length > 0) {
                processCsvFile(e.target.files[0]);
            }
        });
    }

    if (demoBtn) {
        demoBtn.addEventListener("click", () => {
            const sampleContent = "Company Name,Domain\nStripe,stripe.com\nScale AI,scale.com\nMistral AI,mistral.ai\nElevenLabs,elevenlabs.io\nPostman,postman.com\nCursor,cursor.com\n";
            const sampleBlob = new Blob([sampleContent], { type: "text/csv" });
            const sampleFile = new File([sampleBlob], "tech_startups_demo.csv", { type: "text/csv" });
            processCsvFile(sampleFile);
        });
    }

    if (downloadBtn) {
        downloadBtn.addEventListener("click", () => {
            if (currentEnrichedDownloadId) {
                window.location.href = `${API_BASE}/enrich/download/${currentEnrichedDownloadId}`;
            } else {
                alert("Please upload and enrich a CSV first.");
            }
        });
    }
}

async function processCsvFile(file) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
        alert("Please select a valid .csv file.");
        return;
    }

    const badge = document.getElementById("csv-file-badge");
    const filenameEl = document.getElementById("csv-filename");
    const filesizeEl = document.getElementById("csv-filesize");
    const progressCard = document.getElementById("csv-progress-card");
    const progressBar = document.getElementById("csv-progress-bar");
    const progressStatus = document.getElementById("csv-progress-status");
    const progressPercent = document.getElementById("csv-progress-percent");
    const resultsSection = document.getElementById("csv-results-section");

    if (badge && filenameEl) {
        badge.style.display = "inline-flex";
        filenameEl.textContent = file.name;
        if (filesizeEl) filesizeEl.textContent = `(${Math.max(1, Math.round(file.size / 1024))} KB)`;
    }

    if (resultsSection) resultsSection.style.display = "none";
    if (progressCard) {
        progressCard.style.display = "block";
        progressBar.style.width = "15%";
        progressPercent.textContent = "15%";
        progressStatus.textContent = "Parsing CSV and auto-detecting company columns...";
    }

    const formData = new FormData();
    formData.append("file", file);

    let progressTimer = setInterval(() => {
        let cur = parseInt(progressBar.style.width) || 15;
        if (cur < 85) {
            cur += 15;
            progressBar.style.width = cur + "%";
            progressPercent.textContent = cur + "%";
            if (cur >= 30 && cur < 60) {
                progressStatus.textContent = "Resolving domains & querying Hunter.io API...";
            } else if (cur >= 60) {
                progressStatus.textContent = "Extracting verified decision makers & GitHub commits...";
            }
        }
    }, 600);

    try {
        const res = await authFetch(`${API_BASE}/enrich/csv`, {
            method: "POST",
            body: formData
        });

        clearInterval(progressTimer);

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Enrichment request failed.");
        }

        const data = await res.json();
        progressBar.style.width = "100%";
        progressPercent.textContent = "100%";
        progressStatus.textContent = "Enrichment Complete!";

        setTimeout(() => {
            if (progressCard) progressCard.style.display = "none";
            renderCsvEnrichedResults(data);
        }, 500);

    } catch (err) {
        clearInterval(progressTimer);
        console.error("CSV enrichment error:", err);
        if (progressCard) progressCard.style.display = "none";
        alert(`Failed to enrich CSV: ${err.message}`);
    }
}

function renderCsvEnrichedResults(data) {
    const resultsSection = document.getElementById("csv-results-section");
    const statTotal = document.getElementById("csv-stat-total");
    const statFound = document.getElementById("csv-stat-found");
    const statRate = document.getElementById("csv-stat-rate");
    const tbody = document.getElementById("csv-enriched-tbody");

    currentEnrichedDownloadId = data.download_id;

    if (statTotal) statTotal.textContent = data.total || 0;
    if (statFound) statFound.textContent = data.found_count || 0;
    if (statRate) {
        const rate = data.total > 0 ? Math.round((data.found_count / data.total) * 100) : 0;
        statRate.textContent = `${rate}%`;
    }

    if (tbody) {
        tbody.innerHTML = "";
        const results = data.results || [];
        results.forEach(row => {
            const tr = document.createElement("tr");

            let badgeStyle = "background:rgba(255,255,255,0.06); color:var(--text-muted); border:1px solid rgba(255,255,255,0.1);";
            const src = row.source || "";
            if (src.includes("Hunter")) {
                badgeStyle = "background:rgba(0, 240, 255, 0.12); color:var(--primary-cyan); border:1px solid rgba(0, 240, 255, 0.3);";
            } else if (src.includes("Apollo")) {
                badgeStyle = "background:rgba(168, 85, 247, 0.12); color:#c084fc; border:1px solid rgba(168, 85, 247, 0.3);";
            } else if (src.includes("GitHub")) {
                badgeStyle = "background:rgba(0, 255, 136, 0.12); color:#00ff88; border:1px solid rgba(0, 255, 136, 0.3);";
            }

            tr.innerHTML = `
                <td style="font-weight:600; color:#fff;">${escapeHtml(row.company_name)}</td>
                <td><a href="https://${escapeHtml(row.domain)}" target="_blank" style="color:var(--primary-cyan); text-decoration:none;">${escapeHtml(row.domain)} ↗</a></td>
                <td style="font-weight:500;">${escapeHtml(row.lead_name)}</td>
                <td style="color:var(--text-muted); font-size:13px;">${escapeHtml(row.lead_title)}</td>
                <td>
                    <span style="font-family:'JetBrains Mono', monospace; font-size:13px; color:#fff; background:rgba(255,255,255,0.05); padding:4px 8px; border-radius:6px;">
                        ${escapeHtml(row.lead_email)}
                    </span>
                </td>
                <td>
                    <span style="display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; ${badgeStyle}">
                        ${escapeHtml(row.confidence || row.source)}
                    </span>
                </td>
                <td>
                    <div style="display:flex; gap:6px;">
                        <button class="btn btn-secondary" style="padding:5px 10px; font-size:12px;" onclick="copyToClipboard('${escapeHtml(row.lead_email)}', this)">
                            📋 Copy
                        </button>
                        <button class="btn btn-primary" style="padding:5px 10px; font-size:12px;" onclick="triggerQuickOutreach('${escapeHtml(row.domain)}', '${escapeHtml(row.company_name)}')">
                            ⚡ Pitch
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    if (resultsSection) {
        resultsSection.style.display = "block";
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function copyToClipboard(text, btnEl) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
        const origText = btnEl.textContent;
        btnEl.textContent = "✅ Copied";
        setTimeout(() => { btnEl.textContent = origText; }, 1500);
    }).catch(err => {
        console.warn("Clipboard error:", err);
    });
}

function triggerQuickOutreach(domain, companyName) {
    const input = document.getElementById("manual-domain-input");
    if (input) input.value = domain;
    
    const discoverNav = document.querySelector('.nav-item[data-tab="discover"]');
    if (discoverNav) discoverNav.click();
    
    const manualBtn = document.getElementById("btn-manual-outreach");
    if (manualBtn) manualBtn.click();
}

