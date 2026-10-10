const BACKEND_API = "http://127.0.0.1:8000/api";

document.addEventListener("DOMContentLoaded", async () => {
  const modeBadge = document.getElementById("mode-badge");
  const personFields = document.getElementById("person-fields");
  const personNameInput = document.getElementById("person-name");
  const personTitleInput = document.getElementById("person-title");
  const companyNameInput = document.getElementById("company-name");
  const companyDomainInput = document.getElementById("company-domain");
  const statusEl = document.getElementById("status-box");
  const btnRun = document.getElementById("btn-run-outreach");

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
      
      // 1. Detect profile mode from URL
      if (tab.url && (tab.url.includes("linkedin.com/in/") || tab.url.includes("x.com/") || tab.url.includes("twitter.com/"))) {
        currentContext.mode = "person";
      }

      // 2. Inject content script to parse DOM
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

      // 3. Smart Tab Title Fallback for LinkedIn / Twitter
      if (tab.title && currentContext.mode === "person") {
        const titleStr = tab.title;
        if (titleStr.includes("LinkedIn")) {
          const clean = titleStr.replace("| LinkedIn", "").replace("- LinkedIn", "").trim();
          const parts = clean.split("-").map(p => p.trim());
          
          if (!currentContext.person_name && parts[0]) {
            currentContext.person_name = parts[0];
          }
          if (!currentContext.person_title && parts.length > 1) {
            currentContext.person_title = parts.slice(1).join(" - ");
          }
        }
      }
    }
  } catch (err) {
    console.warn("Tab query error:", err);
  }

  // Derive domain from company name if missing
  if (!currentContext.domain && currentContext.company_name) {
    currentContext.domain = currentContext.company_name.toLowerCase().replace(/[^a-z0-9]/g, "") + ".com";
  }

  // Populate UI
  if (currentContext.mode === "person") {
    modeBadge.textContent = "👤 Person Profile";
    modeBadge.classList.add("person");
    personFields.style.display = "flex";
    personNameInput.value = currentContext.person_name || "";
    personTitleInput.value = currentContext.person_title || "";
  } else {
    modeBadge.textContent = "🏢 Company Page";
    modeBadge.classList.remove("person");
    personFields.style.display = "none";
  }

  companyNameInput.value = currentContext.company_name || "";
  companyDomainInput.value = currentContext.domain || "";

  btnRun.addEventListener("click", async () => {
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (data.status === "CACHED") {
        statusEl.innerHTML = `ℹ️ <strong>Cache Hit!</strong> ${finalDomain} was already scanned. Check Web Dashboard.<br><button id="btn-force-rescan" style="margin-top:10px; width:100%; padding:8px; background:linear-gradient(135deg, #a855f7, #6366f1); color:#fff; border:none; border-radius:6px; font-weight:600; cursor:pointer;">🔄 Force Re-Scan & Replace Pitch</button>`;
        
        document.getElementById("btn-force-rescan")?.addEventListener("click", async () => {
          btnRun.disabled = true;
          statusEl.textContent = `🔄 Force re-scanning ${finalDomain} and generating fresh executive pitch...`;
          try {
            const forceRes = await fetch(`${BACKEND_API}/outreach`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ ...payload, force_refresh: true })
            });
            const forceData = await forceRes.json();
            statusEl.innerHTML = `✅ <strong>Fresh Pitch Created!</strong> Re-scanned ${finalCompanyName || finalDomain}. Check Web Dashboard!`;
          } catch (e) {
            statusEl.textContent = `⚠️ Error re-scanning: ${e}`;
          } finally {
            btnRun.disabled = false;
          }
        });
      } else {
        statusEl.innerHTML = `✅ <strong>Pitch Ready!</strong> Personal outreach created for ${finalPersonName || finalCompanyName}. Open Web Dashboard to approve & send via Gmail!`;
      }
    } catch (err) {
      statusEl.innerHTML = `⚠️ <strong>Backend Offline:</strong> Make sure FastAPI server is running on http://localhost:8000`;
    } finally {
      btnRun.disabled = false;
      btnRun.textContent = "⚡ Generate Outreach Pitch";
    }
  });
});
