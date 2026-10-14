/* ===== StayEasy — админка ===== */
const API = "/api";
const $ = (id) => document.getElementById(id);

const fmtPrice = (n) => new Intl.NumberFormat("ru-RU").format(Math.round(n)) + " ₽";
const fmtDate = (iso) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; };
const TYPE_LABEL = { apartment: "Квартира", room: "Номер" };
const STATUS_LABEL = { pending: "Ожидает", confirmed: "Подтверждена", cancelled: "Отменена" };

let allListings = [];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

async function extractError(res) {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  } catch (_) {}
  return `ошибка (${res.status})`;
}

// ---------- Авторизация ----------
async function tryAuth() {
  try {
    const res = await fetch(`${API}/admin/me`, { credentials: "same-origin" });
    if (!res.ok) return showLogin();
    const me = await res.json();
    enterPanel(me.username);
  } catch (_) {
    showLogin();
  }
}

function showLogin() {
  $("login-view").classList.remove("hidden");
  $("panel-view").classList.add("hidden");
  $("btn-logout").classList.add("hidden");
}

function enterPanel(username) {
  $("login-view").classList.add("hidden");
  $("panel-view").classList.remove("hidden");
  $("btn-logout").classList.remove("hidden");
  $("who").textContent = username;
  loadAllListings().then(() => {
    loadStats();
    loadBookings();
    loadListingsTable();
  });
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errBox = $("login-error");
  errBox.style.display = "none";
  try {
    const res = await fetch(`${API}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ username: $("l-user").value.trim(), password: $("l-pass").value }),
    });
    if (!res.ok) throw new Error(await extractError(res));
    enterPanel($("l-user").value.trim());
  } catch (err) {
    errBox.textContent = err.message;
    errBox.style.display = "block";
  }
});

async function logout() {
  await fetch(`${API}/admin/logout`, { method: "POST", credentials: "same-origin" });
  showLogin();
}

// ---------- Табы ----------
function switchTab(tab) {
  ["dashboard", "bookings", "listings"].forEach((t) =>
    $("tab-" + t).classList.toggle("hidden", t !== tab)
  );
  document.querySelectorAll(".admin-tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab)
  );
}

// ---------- Дашборд ----------
async function loadStats() {
  try {
    const res = await fetch(`${API}/admin/stats`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(await extractError(res));
    const s = await res.json();
    $("stats-grid").innerHTML = `
      ${statCard(fmtPrice(s.revenue_total), "Выручка (все активные брони)", true)}
      ${statCard(fmtPrice(s.revenue_month), "Выручка с начала месяца")}
      ${statCard(s.bookings_pending, "Ждут подтверждения")}
      ${statCard(s.bookings_confirmed, "Подтверждено")}
      ${statCard(s.arriving_today, "Заездов сегодня")}
      ${statCard(s.in_stay, "Сейчас живут")}
      ${statCard(s.upcoming, "Будущих броней")}
      ${statCard(`${s.listings_active}/${s.listings_total}`, "Объекты активны/всего")}
      ${statCard(s.bookings_cancelled, "Отменено")}`;
  } catch (err) {
    $("stats-grid").innerHTML = `<div class="stat-card"><div class="num">⚠️</div><div class="lbl">${esc(err.message)}</div></div>`;
  }
}

const statCard = (num, lbl, accent) =>
  `<div class="stat-card${accent ? " accent" : ""}"><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`;

// ---------- Брони ----------
async function loadAllListings() {
  try {
    const res = await fetch(`${API}/admin/listings`, { credentials: "same-origin" });
    if (res.ok) {
      allListings = await res.json();
      $("bk-listing").innerHTML = `<option value="">Все</option>` +
        allListings.map((l) => `<option value="${l.id}">${esc(l.city)} — ${esc(l.title)}</option>`).join("");
    }
  } catch (_) {}
}

async function loadBookings() {
  const params = new URLSearchParams();
  if ($("bk-search").value.trim()) params.set("search", $("bk-search").value.trim());
  if ($("bk-status").value) params.set("status", $("bk-status").value);
  if ($("bk-listing").value) params.set("listing_id", $("bk-listing").value);
  if ($("bk-from").value) params.set("check_in_from", $("bk-from").value);
  if ($("bk-to").value) params.set("check_in_to", $("bk-to").value);

  const table = $("bookings-table");
  try {
    const res = await fetch(`${API}/admin/bookings?${params}`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(await extractError(res));
    const items = await res.json();
    renderBookingsTable(items);
    renderArrivals(items);
  } catch (err) {
    table.innerHTML = `<tr><td>Ошибка: ${esc(err.message)}</td></tr>`;
  }
}

function renderBookingsTable(items) {
  const rows = items.map((b) => `
    <tr>
      <td><b>#${b.id}</b><br/><span style="color:var(--gray);font-size:12px">${fmtDate(b.created_at.slice(0, 10))}</span></td>
      <td>${esc(b.listing?.title || "объект #" + b.listing_id)}<br/>
          <span style="color:var(--gray);font-size:12px">${esc(b.listing?.city || "")}</span></td>
      <td>${esc(b.guest_name)}<br/>
          <span style="color:var(--gray);font-size:12px">${esc(b.guest_phone)}<br/>${esc(b.guest_email)}</span></td>
      <td>${fmtDate(b.check_in)} → ${fmtDate(b.check_out)}<br/>
          <span style="color:var(--gray);font-size:12px">${b.guests} гост.</span></td>
      <td><b>${fmtPrice(b.total_price)}</b></td>
      <td>
        <select class="mini-select status-${b.status}" onchange="setStatus(${b.id}, this.value)">
          ${Object.entries(STATUS_LABEL).map(([k, v]) =>
            `<option value="${k}" ${k === b.status ? "selected" : ""}>${v}</option>`).join("")}
        </select>
      </td>
      <td>${b.comment ? esc(b.comment) : '<span style="color:var(--gray)">—</span>'}</td>
      <td style="white-space:nowrap">
        <a class="btn btn-ghost" href="/static/admin.html#cal=${b.listing_id}" onclick="openCalForListing(${b.listing_id}); return false;">📅</a>
        <button class="btn btn-danger" onclick="hardDelete(${b.id})" title="Удалить навсегда">✖</button>
      </td>
    </tr>`).join("");
  $("bookings-table").innerHTML = `
    <thead><tr>
      <th>№</th><th>Объект</th><th>Гость</th><th>Даты</th><th>Сумма</th><th>Статус</th><th>Коммент.</th><th></th>
    </tr></thead>
    <tbody>${rows || `<tr><td colspan="8" style="color:var(--gray)">Броней не найдено</td></tr>`}</tbody>`;
}

function renderArrivals(items) {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = items
    .filter((b) => b.status !== "cancelled" && b.check_in >= today)
    .sort((a, b) => a.check_in.localeCompare(b.check_in))
    .slice(0, 8);
  $("arrivals-table").innerHTML = `
    <thead><tr><th>Заезд</th><th>Объект</th><th>Гость</th><th>Ночей</th><th>Статус</th></tr></thead>
    <tbody>${upcoming.map((b) => `
      <tr>
        <td><b>${fmtDate(b.check_in)}</b> → ${fmtDate(b.check_out)}</td>
        <td>${esc(b.listing?.title || "#" + b.listing_id)}</td>
        <td>${esc(b.guest_name)} · ${esc(b.guest_phone)}</td>
        <td>${Math.round((new Date(b.check_out) - new Date(b.check_in)) / 86400000)}</td>
        <td><span class="status status-${b.status}" style="font-size:12px;font-weight:800;padding:4px 10px;border-radius:999px">${STATUS_LABEL[b.status]}</span></td>
      </tr>`).join("") || `<tr><td colspan="5" style="color:var(--gray)">Нет будущих заездов</td></tr>`}</tbody>`;
}

async function setStatus(id, status) {
  const res = await fetch(`${API}/admin/bookings/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ status }),
  });
  if (!res.ok) alert("Не удалось изменить статус: " + (await extractError(res)));
  else { loadStats(); loadBookings(); }
}

async function hardDelete(id) {
  if (!confirm(`Удалить бронь #${id} НАВСЕГДА? Обычно достаточно перевести в «Отменена».`)) return;
  const res = await fetch(`${API}/admin/bookings/${id}`, { method: "DELETE", credentials: "same-origin" });
  if (!res.ok) alert("Ошибка: " + (await extractError(res)));
  else { loadStats(); loadBookings(); }
}

function openCalForListing(id) {
  window.open(`/?listing=${id}`, "_blank");
}

// ---------- Объекты ----------
async function loadListingsTable() {
  try {
    const res = await fetch(`${API}/admin/listings`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(await extractError(res));
    const items = await res.json();
    $("listings-table").innerHTML = `
      <thead><tr><th>ID</th><th>Объект</th><th>Город</th><th>Тип</th><th>Цена/ночь</th><th>Гостей</th><th>Рейтинг</th><th>Статус</th><th></th></tr></thead>
      <tbody>${items.map((l) => `
        <tr style="${l.is_active ? "" : "opacity:.5"}">
          <td>${l.id}</td>
          <td><b>${esc(l.title)}</b><br/><span style="color:var(--gray);font-size:12px">${esc(l.address)}</span></td>
          <td>${esc(l.city)}</td>
          <td>${TYPE_LABEL[l.property_type]}</td>
          <td>${fmtPrice(l.price_per_night)}</td>
          <td>${l.guests}</td>
          <td>⭐ ${l.rating.toFixed(1)}</td>
          <td>${l.is_active ? '<span class="status status-confirmed" style="font-size:12px;font-weight:800;padding:4px 10px;border-radius:999px;background:#d4edda;color:#155724">Активен</span>' : '<span class="status" style="font-size:12px;font-weight:800;padding:4px 10px;border-radius:999px;background:#eee;color:#666">Скрыт</span>'}</td>
          <td style="white-space:nowrap">
            <button class="btn btn-ghost" onclick="toggleListing(${l.id}, ${!l.is_active})" title="Показать/скрыть">${l.is_active ? "🙈 Скрыть" : "👁 Показать"}</button>
          </td>
        </tr>`).join("")}</tbody>`;
  } catch (err) {
    $("listings-table").innerHTML = `<tr><td>Ошибка: ${esc(err.message)}</td></tr>`;
  }
}

async function toggleListing(id, is_active) {
  const res = await fetch(`${API}/admin/listings/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ is_active }),
  });
  if (!res.ok) alert("Ошибка: " + (await extractError(res)));
  else loadListingsTable();
}

// ---------- Старт ----------
tryAuth();
