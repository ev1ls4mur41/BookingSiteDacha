/* ===== StayEasy — логика фронтенда ===== */
const API = "/api";

let currentListing = null;
let currentListingId = null;
let lastBookingEmail = "";

const $ = (id) => document.getElementById(id);

const fmtPrice = (n) => new Intl.NumberFormat("ru-RU").format(Math.round(n)) + " ₽";
const TYPE_LABEL = { apartment: "Квартира", room: "Номер" };
const STATUS_LABEL = { pending: "Ожидает", confirmed: "Подтверждена", cancelled: "Отменена" };

// ---------- Навигация ----------
function showPage(page, emailForBookings) {
  ["search", "detail", "booking", "bookings"].forEach((p) =>
    $("page-" + p).classList.toggle("hidden", p !== page)
  );
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.page === page)
  );
  window.scrollTo(0, 0);
  if (page === "bookings" && emailForBookings) {
    $("lookup-email").value = emailForBookings;
    loadMyBookings();
  }
}

// ---------- Поиск ----------
$("search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const params = new URLSearchParams();
  const city = $("f-city").value.trim();
  const type = $("f-type").value;
  const ci = $("f-checkin").value;
  const co = $("f-checkout").value;
  const guests = $("f-guests").value;
  const maxp = $("f-maxprice").value;

  if (city) params.set("city", city);
  if (type) params.set("type", type);
  if (ci) params.set("check_in", ci);
  if (co) params.set("check_out", co);
  if (guests > 1 || guests) params.set("guests", guests);
  if (maxp) params.set("max_price", maxp);

  try {
    const res = await fetch(`${API}/listings?${params}`);
    if (!res.ok) throw new Error(await extractError(res));
    renderListings(await res.json());
  } catch (err) {
    $("results-info").textContent = "Ошибка: " + err.message;
    $("listings").innerHTML = "";
  }
});

async function extractError(res) {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join("; ");
  } catch (_) {}
  return "сервер недоступен (" + res.status + ")";
}

function renderListings(items) {
  const grid = $("listings");
  $("results-info").textContent = items.length
    ? `Найдено вариантов: ${items.length}`
    : "Ничего не найдено. Попробуйте изменить фильтры или даты.";
  grid.innerHTML = items
    .map(
      (l) => `
      <div class="card" onclick="openDetail(${l.id})">
        <img src="${l.image_url}" alt="${esc(l.title)}" loading="lazy"
             onerror="this.style.display='none'" />
        <div class="card-body">
          <div class="card-type">${TYPE_LABEL[l.property_type] || ""} · до ${l.guests} гост.</div>
          <div class="card-title">${esc(l.title)}</div>
          <div class="card-city">${esc(l.city)}, ${esc(l.address)}</div>
          <div class="card-row">
            <span class="card-rating">⭐ ${l.rating.toFixed(1)}</span>
            <span class="card-price"><b>${fmtPrice(l.price_per_night)}</b> <span>/ ночь</span></span>
          </div>
        </div>
      </div>`
    )
    .join("");
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ---------- Детализация ----------
async function openDetail(id) {
  try {
    const res = await fetch(`${API}/listings/${id}`);
    if (!res.ok) throw new Error(await extractError(res));
    currentListing = await res.json();
    currentListingId = id;

    const amenities = (currentListing.amenities || "")
      .split(",").map((a) => a.trim()).filter(Boolean)
      .map((a) => `<span class="badge">${esc(a)}</span>`).join("");

    $("detail-content").innerHTML = `
      <div class="detail">
        <div>
          <img class="detail-img" src="${currentListing.image_url}" alt="${esc(currentListing.title)}"
               onerror="this.style.display='none'" />
          <h2 style="margin-top:18px">${esc(currentListing.title)}</h2>
          <div class="meta">${TYPE_LABEL[currentListing.property_type]} · ${esc(currentListing.city)}, ${esc(currentListing.address)} · ⭐ ${currentListing.rating.toFixed(1)}</div>
          <div class="badges">
            <span class="badge">👥 До ${currentListing.guests} гостей</span>
            <span class="badge">🛏 Спален: ${currentListing.bedrooms}</span>
            ${amenities}
          </div>
          <p class="detail-desc">${esc(currentListing.description)}</p>
        </div>
        <div class="price-box">
          <div><span class="big">${fmtPrice(currentListing.price_per_night)}</span> <span class="per">/ ночь</span></div>
          <p class="per" style="margin:10px 0 16px">Бесплатная отмена до заезда. Оплата на месте.</p>
          <button class="btn btn-primary btn-lg" style="width:100%" onclick="openBookingForm()">Забронировать</button>
          ${renderCalendar(currentListing.id)}
        </div>
      </div>`;
    showPage("detail");
    loadCalendar();
  } catch (err) {
    alert("Не удалось загрузить объект: " + err.message);
  }
}

// ---------- Календарь занятости ----------
const CAL_MONTHS = ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"];
const CAL_WEEKDAYS = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];
let calYear = null, calMonth = null; // 1..12
let calDays = {};   // "YYYY-MM-DD" -> free|booked|past
let selStart = null, selEnd = null;  // выбранные гостем даты (ISO-строки)

function renderCalendar(id) {
  const now = new Date();
  if (calYear === null) { calYear = now.getFullYear(); calMonth = now.getMonth() + 1; }
  return `
    <div class="calendar" id="calendar">
      <div class="cal-head">
        <button class="cal-nav" onclick="calShift(-1)" aria-label="Предыдущий месяц">‹</button>
        <b id="cal-title">${CAL_MONTHS[calMonth - 1]} ${calYear}</b>
        <button class="cal-nav" onclick="calShift(1)" aria-label="Следующий месяц">›</button>
      </div>
      <div class="cal-grid cal-weekdays">${CAL_WEEKDAYS.map((w) => `<span>${w}</span>`).join("")}</div>
      <div class="cal-grid" id="cal-days"><div class="cal-loading">Загрузка занятости…</div></div>
      <div class="cal-legend">
        <span><i class="dot dot-free"></i> свободно</span>
        <span><i class="dot dot-booked"></i> занято</span>
        <span><i class="dot dot-sel"></i> ваш выбор</span>
      </div>
      <div class="cal-selection" id="cal-selection">Выберите даты прямо в календаре — занятые дни недоступны.</div>
    </div>`;
}

function calShift(delta) {
  let m = calMonth + delta, y = calYear;
  if (m < 1) { m = 12; y--; }
  if (m > 12) { m = 1; y++; }
  const today = new Date();
  if (y < today.getFullYear() || (y === today.getFullYear() && m < today.getMonth() + 1)) return;
  calMonth = m; calYear = y;
  $("cal-title").textContent = `${CAL_MONTHS[m - 1]} ${y}`;
  loadCalendar();
}

async function loadCalendar() {
  const box = $("cal-days");
  if (!box || !currentListing) return;
  try {
    const res = await fetch(`${API}/listings/${currentListing.id}/calendar?year=${calYear}&month=${calMonth}`);
    if (!res.ok) throw new Error(await extractError(res));
    const data = await res.json();
    calDays = {};
    data.days.forEach((d) => (calDays[d.date] = d.status));
    drawCalendarGrid();
  } catch (err) {
    box.innerHTML = `<div class="cal-loading">Календарь недоступен: ${esc(err.message)}</div>`;
  }
}

function isoOf(y, m, d) {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function drawCalendarGrid() {
  const box = $("cal-days");
  if (!box) return;
  const first = new Date(calYear, calMonth - 1, 1);
  const lead = (first.getDay() + 6) % 7; // Пн=0
  const dim = new Date(calYear, calMonth, 0).getDate();
  let html = "";
  for (let i = 0; i < lead; i++) html += "<span></span>";
  for (let d = 1; d <= dim; d++) {
    const iso = isoOf(calYear, calMonth, d);
    const st = calDays[iso] || "free";
    let cls = "cal-day " + st;
    if (selStart && selEnd && iso >= selStart && iso < selEnd) cls += " in-range";
    if (selStart && iso === selStart) cls += " sel-edge";
    if (selEnd && iso === selEnd) cls += " sel-edge"; // день выезда подсвечиваем рамкой
    if (st === "free") {
      html += `<button class="${cls}" onclick="calPick('${iso}')">${d}</button>`;
    } else {
      html += `<span class="${cls}">${d}</span>`;
    }
  }
  box.innerHTML = html;
  updateCalSelection();
}

function rangeBlocked(fromIso, toIso) {
  // проверка: все ночи [from, to) должны быть free и не past
  let d = new Date(fromIso + "T00:00:00");
  const end = new Date(toIso + "T00:00:00");
  while (d < end) {
    const iso = d.toISOString().slice(0, 10);
    const st = calDays[iso];
    if (st === "booked" || st === "past") return true;
    d.setDate(d.getDate() + 1);
  }
  return false;
}

function calPick(iso) {
  if (!selStart || (selStart && selEnd)) {
    // начало нового выбора
    selStart = iso; selEnd = null;
  } else if (iso <= selStart) {
    selStart = iso; // сдвигаем заезд
  } else {
    // выезд — можно выбрать даже "занятый" день (это день освобождения),
    // но все ночи между должны быть свободны
    if (rangeBlocked(selStart, iso)) {
      flashCalMsg("Между выбранными датами есть занятые дни ⛔", true);
      selStart = iso; selEnd = null;
    } else {
      selEnd = iso;
    }
  }
  syncCalToForm();
  drawCalendarGrid();
}

function syncCalToForm() {
  if (selStart) $("b-checkin").value = selStart;
  if (selEnd) $("b-checkout").value = selEnd;
  recalcTotal();
}

function updateCalSelection() {
  const el = $("cal-selection");
  if (!el) return;
  if (selStart && selEnd) {
    const nights = Math.round((new Date(selEnd) - new Date(selStart)) / 86400000);
    el.innerHTML = `📅 Заезд <b>${selStart}</b> → выезд <b>${selEnd}</b> · ${nights} ноч.`;
    el.classList.remove("cal-warn");
  } else if (selStart) {
    el.textContent = "Теперь выберите дату выезда.";
    el.classList.remove("cal-warn");
  } else {
    el.textContent = "Выберите даты прямо в календаре — занятые дни недоступны.";
    el.classList.remove("cal-warn");
  }
}

function flashCalMsg(text, warn) {
  const el = $("cal-selection");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("cal-warn", !!warn);
}

// ---------- Форма бронирования ----------
function openBookingForm() {
  const l = currentListing;
  $("booking-summary").innerHTML = `
    <img src="${l.image_url}" alt="" onerror="this.style.display='none'" />
    <div>
      <b>${esc(l.title)}</b><br/>
      <span style="color:var(--gray)">${esc(l.city)}, ${esc(l.address)} · ${fmtPrice(l.price_per_night)}/ночь</span>
    </div>`;

  // даты берутся из выбора в календаре, иначе — из поиска
  $("b-checkin").value = selStart || $("f-checkin").value || "";
  $("b-checkout").value = selEnd || $("f-checkout").value || "";
  $("b-guests").value = $("f-guests").value || 1;
  $("b-guests").max = l.guests;
  $("booking-error").classList.add("hidden");
  recalcTotal();
  showPage("booking");
}

function recalcTotal() {
  const ci = $("b-checkin").value, co = $("b-checkout").value;
  if (!ci || !co || new Date(co) <= new Date(ci)) {
    $("booking-total").textContent = "Укажите корректные даты, чтобы увидеть итоговую стоимость.";
    return null;
  }
  const nights = Math.round((new Date(co) - new Date(ci)) / 86400000);
  const total = nights * currentListing.price_per_night;
  $("booking-total").textContent = `${nights} ноч. × ${fmtPrice(currentListing.price_per_night)} = ${fmtPrice(total)}`;
  return { nights, total };
}

["b-checkin", "b-checkout"].forEach((id) => $(id).addEventListener("change", recalcTotal));

$("booking-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errBox = $("booking-error");
  errBox.classList.add("hidden");

  const payload = {
    listing_id: currentListing.id,
    guest_name: $("b-name").value.trim(),
    guest_phone: $("b-phone").value.trim(),
    guest_email: $("b-email").value.trim(),
    check_in: $("b-checkin").value,
    check_out: $("b-checkout").value,
    guests: Number($("b-guests").value),
    comment: $("b-comment").value.trim(),
  };

  try {
    const res = await fetch(`${API}/bookings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await extractError(res));
    const booking = await res.json();
    lastBookingEmail = payload.guest_email;
    $("modal-text").innerHTML =
      `Номер брони: <b>#${booking.id}</b><br/>` +
      `${esc(booking.listing?.title || currentListing.title)}, ` +
      `${booking.check_in} → ${booking.check_out}<br/>Итого: <b>${fmtPrice(booking.total_price)}</b>`;
    $("modal").classList.remove("hidden");
    $("booking-form").reset();
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
});

function closeModal() {
  $("modal").classList.add("hidden");
}

// ---------- Мои брони ----------
async function loadMyBookings() {
  const email = $("lookup-email").value.trim();
  const box = $("bookings-list");
  if (!email) {
    box.innerHTML = "<p style='color:var(--gray)'>Введите e-mail, которым бронировали.</p>";
    return;
  }
  try {
    const res = await fetch(`${API}/bookings?guest_email=${encodeURIComponent(email)}`);
    if (!res.ok) throw new Error(await extractError(res));
    const items = await res.json();
    if (!items.length) {
      box.innerHTML = "<p style='color:var(--gray)'>Броней не найдено.</p>";
      return;
    }
    box.innerHTML = items.map(renderBookingItem).join("");
  } catch (err) {
    box.innerHTML = "<p class='error' style='display:block'>Ошибка: " + esc(err.message) + "</p>";
  }
}

function renderBookingItem(b) {
  const title = b.listing ? esc(b.listing.title) : "Объект #" + b.listing_id;
  return `
    <div class="booking-item">
      <div>
        <b>#${b.id} — ${title}</b><br/>
        <span style="color:var(--gray)">${b.check_in} → ${b.check_out} · ${b.guests} гост. · ${fmtPrice(b.total_price)}</span>
      </div>
      <div style="display:flex; align-items:center; gap:12px">
        <span class="status status-${b.status}">${STATUS_LABEL[b.status]}</span>
        ${b.status !== "cancelled" ? `<button class="btn btn-danger" onclick="cancelBooking(${b.id})">Отменить</button>` : ""}
      </div>
    </div>`;
}

async function cancelBooking(id) {
  if (!confirm("Отменить бронь #" + id + "?")) return;
  const email = $("lookup-email").value.trim();
  try {
    const res = await fetch(`${API}/bookings/${id}?guest_email=${encodeURIComponent(email)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await extractError(res));
    loadMyBookings();
  } catch (err) {
    alert("Не удалось отменить: " + err.message);
  }
}

// ---------- live-проверка занятости при смене дат в форме ----------
async function liveAvailabilityCheck() {
  const ci = $("b-checkin").value, co = $("b-checkout").value;
  const box = $("booking-error");
  if (!currentListing || !ci || !co || new Date(co) <= new Date(ci)) return;
  try {
    const res = await fetch(`${API}/listings/${currentListing.id}/availability?check_in=${ci}&check_out=${co}`);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.available) {
      box.textContent = "⚠️ Эти даты только что заняли. Выберите другие в календаре на странице объекта.";
      box.classList.remove("hidden");
    } else {
      box.classList.add("hidden");
    }
  } catch (_) {}
}

["b-checkin", "b-checkout"].forEach((id) => $(id).addEventListener("change", liveAvailabilityCheck));

// ---------- Инициализация ----------
(async function init() {
  // сброс выбора календаря при входе на страницу объекта
  const origOpen = openDetail;
  window.openDetail = async function (id) {
    selStart = null; selEnd = null; calDays = {};
    const now = new Date();
    calYear = now.getFullYear(); calMonth = now.getMonth() + 1;
    await origOpen(id);
  };

  // ставим минимальную дату заезда = сегодня
  const today = new Date().toISOString().slice(0, 10);
  $("f-checkin").min = today;
  $("f-checkout").min = today;
  $("b-checkin").min = today;
  $("b-checkout").min = today;

  // первичная загрузка всех объектов
  const res = await fetch(`${API}/listings`);
  if (res.ok) renderListings(await res.json());

  // прямая ссылка /?listing=ID — открыть карточку объекта (для админки)
  const params = new URLSearchParams(location.search);
  const lid = Number(params.get("listing"));
  if (lid > 0) openDetail(lid);
})();
