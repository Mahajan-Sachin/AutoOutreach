(() => {
  const url = window.location.href;
  const hostname = window.location.hostname;

  let result = {
    mode: "company", // "person" or "company"
    domain: "",
    company_name: "",
    person_name: "",
    person_title: "",
    profile_url: url,
    source: "generic"
  };

  try {
    if (hostname.includes("linkedin.com")) {
      result.source = "linkedin";
      if (url.includes("/in/")) {
        result.mode = "person";
        
        // 1. Target the Top Profile Header Card using h1.closest('section')
        const h1El = document.querySelector('h1');
        const topCard = h1El ? (h1El.closest('section') || h1El.closest('div.ph5')) : (document.querySelector('main section:first-of-type') || document.querySelector('.pv-top-card'));

        if (h1El && h1El.innerText) {
          result.person_name = h1El.innerText.replace(/✔| Verified/g, '').split('\n')[0].trim();
        }

        if (topCard && topCard.innerText) {
          const rawLines = topCard.innerText.split('\n').map(l => l.trim()).filter(l => l.length > 0 && !l.includes('connection') && !l.includes('Contact info') && !l.includes('mutual') && !l.includes('followers'));

          for (let i = 0; i < Math.min(rawLines.length, 8); i++) {
            const line = rawLines[i];
            if (line !== result.person_name && (line.includes('@') || line.toLowerCase().includes(' at ') || line.match(/CTO|CEO|Founder|Director|Lead|Head|Engineer|Manager|VP|President|Co-founder|Chief/i))) {
              result.person_title = line;
              break;
            }
          }
          if (!result.person_title && rawLines.length > 1) {
            result.person_title = rawLines[1] !== result.person_name ? rawLines[1] : (rawLines[2] || "");
          }
        }

        // Document Title Parsing Backup
        const docTitle = (document.title || "").replace(/^\(\d+\)\s*/, '');
        if (docTitle.includes("LinkedIn")) {
          const cleanTitle = docTitle.replace("| LinkedIn", "").replace("- LinkedIn", "").trim();
          const parts = cleanTitle.split("-").map(p => p.trim());

          if (!result.person_name && parts.length > 0) {
            result.person_name = parts[0];
          }
          if (!result.person_title && parts.length > 1) {
            result.person_title = parts.slice(1).join(" - ");
          }

          const fullText = result.person_title || cleanTitle;
          if (fullText.includes("@")) {
            const comp = fullText.split("@")[1].trim().split("-")[0].split("|")[0].split("·")[0].trim();
            if (comp) result.company_name = comp;
          } else if (fullText.toLowerCase().includes(" at ")) {
            const comp = fullText.split(/ at /i)[1].trim().split("-")[0].split("|")[0].split("·")[0].trim();
            if (comp) result.company_name = comp;
          }
        }

        if (!result.company_name && result.person_title) {
          if (result.person_title.includes("@")) {
            result.company_name = result.person_title.split("@")[1].trim().split("-")[0].split("|")[0].split("·")[0].trim();
          } else if (result.person_title.toLowerCase().includes(" at ")) {
            result.company_name = result.person_title.split(/ at /i)[1].trim().split("-")[0].split("|")[0].split("·")[0].trim();
          }
        }

        if (!result.company_name && topCard) {
          const compEl = topCard.querySelector('button[aria-label*="Current company"]') ||
                         topCard.querySelector('span[aria-label*="Current company"]') ||
                         topCard.querySelector('a[href*="/company/"]');
          if (compEl && compEl.innerText) {
            result.company_name = compEl.innerText.split('\n')[0].split('·')[0].trim();
          }
        }

        const externalLink = document.querySelector('a.pv-contact-info__contact-link[href*="http"]:not([href*="linkedin.com"])');
        if (externalLink && externalLink.href) {
          try {
            const u = new URL(externalLink.href);
            result.domain = u.hostname.replace('www.', '');
          } catch(e) {}
        }
      } else if (url.includes("/company/")) {
        result.mode = "company";
        
        // Extract clean company name without notification counts like (4)
        const orgNameEl = document.querySelector('h1') || document.querySelector('.org-top-card-summary__title');
        if (orgNameEl && orgNameEl.innerText) {
          result.company_name = orgNameEl.innerText.replace(/^\(\d+\)\s*/, '').split('\n')[0].trim();
        } else if (document.title) {
          const cleanDoc = document.title.replace(/^\(\d+\)\s*/, '');
          result.company_name = cleanDoc.split(':')[0].split('-')[0].split('|')[0].trim();
        }

        // Extract website domain link from LinkedIn company page
        const websiteEl = document.querySelector('a[href*="http"]:not([href*="linkedin.com"])') ||
                          document.querySelector('a[aria-label*="Website"]') ||
                          document.querySelector('a[data-test-id*="website"]') ||
                          document.querySelector('section[class*="top-card"] a[href*="http"]');
        if (websiteEl && websiteEl.href) {
          try {
            const u = new URL(websiteEl.href);
            result.domain = u.hostname.replace('www.', '');
          } catch(e) {}
        }
      }
    } else if (hostname.includes("x.com") || hostname.includes("twitter.com")) {
      result.source = "twitter";
      result.mode = "person";

      const nameEl = document.querySelector('[data-testid="User-Name"]');
      if (nameEl && nameEl.innerText) {
        const text = nameEl.innerText.split('\n');
        result.person_name = text[0].trim();
      }

      const bioEl = document.querySelector('[data-testid="UserDescription"]');
      if (bioEl && bioEl.innerText) {
        result.person_title = bioEl.innerText.trim();
        const match = result.person_title.match(/(?:Founder|CTO|CEO|Co-founder|Building)\s+(?:at|@)\s+([A-Za-z0-9_\-\.]+)/i);
        if (match && match[1]) {
          result.company_name = match[1].trim();
        }
      }

      const urlEl = document.querySelector('[data-testid="UserUrl"]');
      if (urlEl) {
        const rawUrl = urlEl.innerText || urlEl.getAttribute('href');
        if (rawUrl) {
          let clean = rawUrl.replace('https://', '').replace('http://', '').split('/')[0].replace('www.', '');
          result.domain = clean;
        }
      }
    } else {
      result.mode = "company";
      result.domain = hostname.replace('www.', '');
      result.company_name = document.title ? document.title.replace(/^\(\d+\)\s*/, '').split('-')[0].split('|')[0].split(':')[0].trim() : result.domain.split('.')[0].toUpperCase();
    }
  } catch (err) {
    console.error("DOM Scraper Error:", err);
  }

  // Clean company name if contains notification count or title suffix
  if (result.company_name) {
    result.company_name = result.company_name.replace(/^\(\d+\)\s*/, '').split(':')[0].trim();
  }

  // Fallback domain creation from clean company name
  if (!result.domain && result.company_name) {
    result.domain = result.company_name.toLowerCase().replace(/[^a-z0-9]/g, '') + '.com';
  }

  return result;
})();
