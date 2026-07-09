const DAILY_LIMIT = 20;
const API_BASE = "";

let telegramId   = null;
let initDataRaw  = "";
let userData     = null;
let adInProgress = false;

const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#1c1c1e");
  tg.setBackgroundColor("#1c1c1e");
}

function showToast(message, type = "", duration = 2800) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className   = "show" + (type ? ` ${type}` : "");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.className = ""; }, duration);
}

function formatCA(n) {
  const val = parseFloat(n ?? 0);
  return val % 1 === 0 ? val.toFixed(0) : val.toFixed(1);
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso + "Z").toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch { return iso; }
}

function setLoading(visible) {
  const overlay = document.getElementById("loading-overlay");
  if (visible) overlay.classList.remove("hidden");
  else overlay.classList.add("hidden");
}

async function apiFetch(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initDataRaw,
    },
    ...options,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || "API error");
  return json;
}

function generateUUID() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

async function fetchUser(id)         { return apiFetch(`/api/user/${id}`); }
async function fetchReferralLink(id) { return apiFetch(`/api/referral-link/${id}`); }
async function fetchReferrals(id)    { return apiFetch(`/api/referrals/${id}`); }

async function postAdWatched(requestId) {
  return apiFetch("/api/ad-watched", {
    method: "POST",
    body: JSON.stringify({ request_id: requestId }),
  });
}

function updateHeaderBalance(balance, adsToday) {
  document.getElementById("balance-display").textContent = formatCA(balance);
  document.getElementById("ads-today").textContent       = adsToday;
}

function updateWatchAdSection(adsToday) {
  const pct = Math.min((adsToday / DAILY_LIMIT) * 100, 100);
  document.getElementById("limit-bar").style.width   = pct + "%";
  document.getElementById("limit-label").textContent = `${adsToday} / ${DAILY_LIMIT} today`;

  const btn = document.getElementById("watch-ad-btn");
  if (adsToday >= DAILY_LIMIT) {
    btn.disabled    = true;
    btn.textContent = "✅ Daily limit reached";
  } else {
    btn.disabled  = false;
    btn.innerHTML = "▶&nbsp; Watch Ad";
  }
}

function updateBalanceSection(data) {
  document.getElementById("bal-display").textContent        = formatCA(data.ca_balance);
  document.getElementById("stat-ads-today").textContent     = data.ads_watched_today;
  document.getElementById("stat-ads-remaining").textContent = data.ads_remaining_today;
  document.getElementById("stat-total-ads").textContent     = data.total_ads_watched;
  document.getElementById("stat-ref-ca").textContent        = formatCA(data.referral_ca_earned) + " CA";
  document.getElementById("wd-balance").textContent         = formatCA(data.ca_balance);
}

function updateProfileSection(data) {
  const initial = (data.first_name || data.username || "?")[0].toUpperCase();
  document.getElementById("avatar-circle").textContent    = initial;
  document.getElementById("profile-name").textContent     = data.first_name || data.username || "User";
  document.getElementById("profile-id").textContent       = `ID: ${data.telegram_id}`;
  document.getElementById("prof-username").textContent    = data.username ? `@${data.username}` : "—";
  document.getElementById("prof-telegram-id").textContent = data.telegram_id;
  document.getElementById("prof-join-date").textContent   = formatDate(data.join_date);
  document.getElementById("prof-balance").textContent     = formatCA(data.ca_balance) + " CA";
}

function renderReferralSection(userData, refData, refLink) {
  document.getElementById("ref-link-text").textContent  = refLink;
  document.getElementById("ref-count").textContent      = refData.referral_count;
  document.getElementById("ref-ca-earned").textContent  = formatCA(refData.referral_ca_earned) + " CA";

  const card = document.getElementById("ref-friends-card");
  const list = document.getElementById("ref-friends-list");

  if (refData.referred_users && refData.referred_users.length > 0) {
    card.style.display = "block";
    list.innerHTML = refData.referred_users.map(u => `
      <div class="stat-row">
        <span class="stat-label">${u.first_name || u.username || "User"} ${u.username ? "<small style='color:var(--text-dim)'>@" + u.username + "</small>" : ""}</span>
        <span class="stat-value" style="font-size:12px;color:var(--text-sec)">${formatDate(u.date)}</span>
      </div>
    `).join("");
  } else {
    card.style.display = "none";
  }
}

function applyUserData(data) {
  userData = data;
  updateHeaderBalance(data.ca_balance, data.ads_watched_today);
  updateWatchAdSection(data.ads_watched_today);
  updateBalanceSection(data);
  updateProfileSection(data);
}

function showAd() {
  return show_11245779();
}

async function onWatchAdClicked() {
  if (adInProgress) return;
  if (!telegramId || !initDataRaw) { showToast("❌ Not logged in", "error"); return; }

  if (userData && userData.ads_watched_today >= DAILY_LIMIT) {
    showToast("📵 Daily limit reached. Come back tomorrow!", "error");
    return;
  }

  adInProgress = true;
  const btn = document.getElementById("watch-ad-btn");
  btn.disabled    = true;
  btn.textContent = "⏳ Loading ad…";

  const requestId = generateUUID();

  try {
    await showAd();
    await onAdComplete(requestId);
  } catch (err) {
    onAdSkipped(err);
  } finally {
    adInProgress = false;
  }
}

async function onAdComplete(requestId) {
  const btn = document.getElementById("watch-ad-btn");
  btn.textContent = "⏳ Claiming reward…";

  try {
    const result = await postAdWatched(requestId);

    if (userData) {
      userData.ca_balance          = result.new_balance;
      userData.ads_watched_today   = result.ads_watched_today;
      userData.ads_remaining_today = result.ads_remaining;
    }

    updateHeaderBalance(result.new_balance, result.ads_watched_today);
    updateWatchAdSection(result.ads_watched_today);
    updateBalanceSection(userData || {
      ca_balance:          result.new_balance,
      ads_watched_today:   result.ads_watched_today,
      ads_remaining_today: result.ads_remaining,
      total_ads_watched:   (userData?.total_ads_watched ?? 0) + 1,
      referral_ca_earned:  userData?.referral_ca_earned ?? 0,
    });

    showToast(`+${result.ca_earned} CA earned! 🎉`, "success");

  } catch (err) {
    showToast("⚠️ Reward failed: " + err.message, "error");
  }
}

function onAdSkipped(err) {
  showToast("Ad was skipped — no reward earned.", "");
  updateWatchAdSection(userData?.ads_watched_today ?? 0);
}

document.getElementById("copy-link-btn").addEventListener("click", async () => {
  const text = document.getElementById("ref-link-text").textContent;
  if (!text || text === "Loading…") return;
  try {
    await navigator.clipboard.writeText(text);
    showToast("✅ Link copied!", "success");
  } catch {
    const el = document.getElementById("ref-link-text");
    const range = document.createRange();
    range.selectNode(el);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    try { document.execCommand("copy"); showToast("✅ Link copied!", "success"); }
    catch { showToast("Copy this link manually", ""); }
    window.getSelection().removeAllRanges();
  }
});

document.querySelectorAll(".nav-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    const name = tab.dataset.tab;
    document.querySelectorAll(".nav-tab").forEach(t => {
      t.classList.toggle("active", t === tab);
      t.setAttribute("aria-selected", t === tab ? "true" : "false");
    });
    document.querySelectorAll(".section").forEach(s => {
      s.classList.toggle("active", s.id === `section-${name}`);
    });
  });
});

document.getElementById("watch-ad-btn").addEventListener("click", onWatchAdClicked);

async function boot() {
  setLoading(true);

  initDataRaw = tg?.initData || "";
  const tgUser = tg?.initDataUnsafe?.user;

  if (tgUser?.id) {
    telegramId = tgUser.id;
  } else {
    const params = new URLSearchParams(window.location.search);
    telegramId = parseInt(params.get("tgid") || "0", 10) || null;

    if (!telegramId) {
      setLoading(false);
      showToast("⚠️ Open this app inside Telegram.", "error", 8000);
      document.getElementById("balance-display").textContent = "—";
      return;
    }
  }

  try {
    const [user, refData, refLinkData] = await Promise.all([
      fetchUser(telegramId),
      fetchReferrals(telegramId),
      fetchReferralLink(telegramId),
    ]);

    applyUserData({ ...user, referral_ca_earned: refData.referral_ca_earned });
    renderReferralSection(user, refData, refLinkData.referral_link);

  } catch (err) {
    showToast("⚠️ Could not load data. " + (err.message || ""), "error");
    document.getElementById("balance-display").textContent = "—";
  } finally {
    setLoading(false);
  }
}

boot();
