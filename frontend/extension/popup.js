const BACKEND_API = "http://4.145.88.53:8000/api";

document.addEventListener("DOMContentLoaded", async () => {
  const authSection = document.getElementById("auth-section");
  const mainSection = document.getElementById("main-section");
  const authUsernameInput = document.getElementById("auth-username");
  const authPasswordInput = document.getElementById("auth-password");
  const authError = document.getElementById("auth-error");
  const btnLogin = document.getElementById("btn-login");
  const btnLogout = document.getElementById("btn-logout");
  const userDisplay = document.getElementById("user-display");

  const modeBadge = document.getElementById("mode-badge");
  const personFields = document.getElementById("person-fields");
  const personNameInput = document.getElementById("person-name");
  const personTitleInput = document.getElementById("person-title");
  const companyNameInput = document.getElementById("company-name");
  const companyDomainInput = document.getElementById("company-domain");
  const statusEl = document.getElementById("status-box");
  const btnRun = document.getElementById("btn-run-outreach");

  let authToken = null;

  // 1. Check existing JWT auth session
  chrome.storage.local.get(["jobfit_token", "jobfit_user"], async (result) => {
    if (result.jobfit_token) {
      authToken = result.jobfit_token;
      showAuthenticated(result.jobfit_user || "sachin");
    } else {
      showUnauthenticated();
    }
  });

  function showAuthenticated(username) {
    authSection.style.display = "none";
    mainSection.style.display = "block";
    userDisplay.textContent = `🟢 @${username} (Admin)`;
    statusEl.textContent = "Authenticated via JWT. Ready to generate 1-click tailored pitches.";
  }

  function showUnauthenticated() {
    authSection.style.display = "block";
    mainSection.style.display = "none";
    statusEl.textContent = "Please sign in to unlock access to your Azure outreach engine.";
  }

  // 2. Login Event
  btnLogin.addEventListener("click", async () => {
    const username = authUsernameInput.value.trim();
    const password = authPasswordInput.value.trim();

    if (!username || !password) {
      authError.textContent = "Please enter username and password.";
      authError.style.display = "block";
      return;
    }

    btnLogin.disabled = true;
    btnLogin.textContent = "Verifying...";
    authError.style.display = "none";

    try {
      const res = await fetch(`${BACKEND_API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Invalid credentials.");
      }

      const data = await res.json();
      authToken = data.access_token;
      chrome.storage.local.set({ jobfit_token: authToken, jobfit_user: data.username }, () => {
        showAuthenticated(data.username);
      });
    } catch (err) {
      authError.textContent = `⚠️ ${err.message}`;
      authError.style.display = "block";
    } finally {
      btnLogin.disabled = false;
      btnLogin.textContent = "🔑 Sign In with JWT";
    }
  });

  // 3. Logout Event
  btnLogout.addEventListener("click", () => {
    authToken = null;
    chrome.storage.local.remove(["jobfit_token", "jobfit_user"], () => {
      showUnauthenticated();
    });
  });

  // 4. Tab Context Detection
  let currentContext = {
    mode: "company",
    domain: "",
    company_name: "",
    person_name: "",
    person_title: "",
    profile_url: ""
  };

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      currentContext.profile_url = tab.url || "";
      
      if (tab.url && (tab.url.includes("linkedin.com/in/") || tab.url.includes("x.com/") || tab.url.includes("twitter.com/"))) {
        currentContext.mode = "person";
      }

      try {
        const results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["content.js"]
        });

        if (results && results[0] && results[0].result) {
          currentContext = { ...currentContext, ...results[0].result };
        }
      } catch (scriptErr) {
        console.warn("Script execution fallback:", scriptErr);
      }

      if (tab.title && currentContext.mode === "person") {
        const titleStr = tab.title;
        if (titleStr.includes("LinkedIn")) {
          const clean = titleStr.replace("| LinkedIn", "").replace("- LinkedIn", "").trim();
          if (clean.includes(" - ")) {
            const parts = clean.split(" - ");
            currentContext.person_name = currentContext.person_name || parts[0].trim();
            currentContext.person_title = currentContext.person_title || parts[1].trim();
          }
        }
      }
    }
  } catch (e) {
    console.error("Tab detection error:", e);
  }

  if (currentContext.mode === "person") {
    modeBadge.textContent = "👤 Person Mode";
    modeBadge.classList.add("person");
    personFields.style.display = "flex";
    personNameInput.value = currentContext.person_name || "";
    personTitleInput.value = currentContext.person_title || "";
  } else {
    modeBadge.textContent = "🏢 Company Mode";
    modeBadge.classList.remove("person");
    personFields.style.display = "none";
  }

  companyNameInput.value = currentContext.company_name || "";
  companyDomainInput.value = currentContext.domain || "";

  // 5. Generate Outreach Pitch Click Handler
  btnRun.addEventListener("click", async () => {
    if (!authToken) {
      statusEl.textContent = "⚠️ Please sign in first.";
      showUnauthenticated();
      return;
    }

    const finalDomain = companyDomainInput.value.trim().toLowerCase().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "");
    const finalCompanyName = companyNameInput.value.trim();
    const finalPersonName = personNameInput.value.trim();
    const finalPersonTitle = personTitleInput.value.trim();

    if (!finalDomain && !finalCompanyName && !finalPersonName) {
      statusEl.textContent = "⚠️ Please enter a target person or company name.";
      return;
    }

    btnRun.disabled = true;
    btnRun.textContent = "🌀 Executing Agent...";
    statusEl.textContent = currentContext.mode === "person"
      ? `Analyzing ${finalPersonName || "profile"} at ${finalCompanyName || finalDomain}, looking up direct email...`
      : `Scanning ${finalDomain}, evaluating tech stack, and discovering decision makers...`;

    const payload = {
      mode: currentContext.mode,
      domain: finalDomain,
      company_name: finalCompanyName,
      person_name: finalPersonName,
      person_title: finalPersonTitle,
      profile_url: currentContext.profile_url
    };

    try {
      const res = await fetch(`${BACKEND_API}/outreach`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${authToken}`
        },
        body: JSON.stringify(payload)
      });

      if (res.status === 401) {
        statusEl.innerHTML = `⚠️ <strong>Unauthorized:</strong> Session token expired. Please log in again.`;
        showUnauthenticated();
        return;
      }

      const data = await res.json();

      if (data.status === "CACHED") {
        statusEl.innerHTML = `ℹ️ <strong>Cache Hit!</strong> ${finalDomain} was already scanned. Check Web Dashboard.`;
      } else {
        statusEl.innerHTML = `✅ <strong>Pitch Ready!</strong> Personal outreach created for ${finalPersonName || finalCompanyName}. Open Web Dashboard to approve & send via Gmail!`;
      }
    } catch (err) {
      statusEl.innerHTML = `⚠️ <strong>Error:</strong> Failed to reach Azure backend at ${BACKEND_API}`;
    } finally {
      btnRun.disabled = false;
      btnRun.textContent = "⚡ Generate Outreach Pitch";
    }
  });
});
