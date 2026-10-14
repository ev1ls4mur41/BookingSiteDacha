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
        </div>
      </div>`;
    showPage("detail");
  } catch (err) {
    alert("Не удалось загрузить объект: " + err.message);
  }
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

  // переносим даты из поиска, если заданы
  $("b-checkin").value = $("f-checkin").value || "";
  $("b-checkout").value = $("f-checkout").value || "";
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
  try {
    const res = await fetch(`${API}/bookings/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await extractError(res));
    loadMyBookings();
  } catch (err) {
    alert("Не удалось отменить: " + err.message);
  }
}

// ---------- Инициализация ----------
(async function init() {
  // ставим минимальную дату заезда = сегодня
  const today = new Date().toISOString().slice(0, 10);
  $("f-checkin").min = today;
  $("f-checkout").min = today;
  $("b-checkin").min = today;
  $("b-checkout").min = today;

  // первичная загрузка всех объектов
  const res = await fetch(`${API}/listings`);
  if (res.ok) renderListings(await res.json());
})();
