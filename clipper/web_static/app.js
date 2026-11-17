"use strict";
// Clipper Studio — UI satu halaman tanpa build step. Semua data lewat /api.

const $ = (s, el = document) => el.querySelector(s);
const isi = $("#isi");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mmss = (d) => {
  d = Math.max(0, Number(d) || 0);
  const m = Math.floor(d / 60), s = d - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
};
const simpanLokal = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} };
const bacaLokal = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (_) { return d; } };

// Ikon lokal: antarmuka tetap lengkap tanpa CDN atau font eksternal.
const IKON = {
  video: '<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
  settings: '<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="m8.2 8.2 12 12M8.2 15.8 20 4M14 10l-2 2"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  back: '<path d="M19 12H5m5-5-5 5 5 5"/>',
  link: '<path d="m10 13 4-4m-6 6-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 6 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(2 0)"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  refresh: '<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  moon: '<path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z"/>',
  auto: '<circle cx="12" cy="12" r="9"/><path d="M12 3v18M12 3a9 9 0 0 1 0 18Z" fill="currentColor" stroke="none"/>',
};
const ikon = (nama) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IKON[nama] || IKON.video}</svg>`;
document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = ikon(el.dataset.icon); });
$(".lewati").onclick = (e) => { e.preventDefault(); isi.focus(); isi.scrollIntoView({ block: "start" }); };
const kosong = (nama, judul, ket, aksi = "") => `<div class="kosong">${ikon(nama)}<strong>${esc(judul)}</strong><p>${esc(ket)}</p>${aksi}</div>`;
function namaSumber(asal) {
  try {
    const u = new URL(asal);
    const host = u.hostname.replace(/^www\./, "");
    if (host === "youtu.be" || host === "youtube.com" || host.endsWith(".youtube.com")) {
      const id = u.searchParams.get("v") || u.pathname.split("/").filter(Boolean).pop();
      return `Video YouTube${id ? ` · ${id}` : ""}`;
    }
    return `Video dari ${host}`;
  } catch (_) { return String(asal || "Video tanpa judul").split(/[\\/]/).pop(); }
}
function siapkanTab() {
  isi.querySelectorAll('[role="tablist"]').forEach((list, n) => {
    const tabs = [...list.querySelectorAll("button")];
    const sinkron = () => tabs.forEach((b) => {
      const aktif = b.classList.contains("aktif");
      b.setAttribute("aria-selected", String(aktif));
      b.tabIndex = aktif ? 0 : -1;
    });
    tabs.forEach((b, i) => {
      b.setAttribute("role", "tab");
      b.id ||= `tab-${n}-${i}`;
      const key = b.dataset.mode || b.dataset.tab;
      const panel = isi.querySelector(`[data-bagian="${key}"], [data-isi="${key}"]`);
      if (panel) {
        panel.id ||= `panel-${n}-${i}`;
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", b.id);
        b.setAttribute("aria-controls", panel.id);
      }
      b.addEventListener("click", sinkron);
      b.addEventListener("keydown", (e) => {
        const j = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i + tabs.length - 1) % tabs.length : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : -1;
        if (j < 0) return;
        e.preventDefault(); tabs[j].focus(); tabs[j].click();
      });
    });
    sinkron();
  });
}

async function api(path, opt = {}) {
  const o = { ...opt, headers: { ...(opt.headers || {}) } };
  if (o.method && o.method !== "GET") o.headers["X-Clipper"] = "1";
  if (o.json !== undefined) {
    o.body = JSON.stringify(o.json);
    o.headers["Content-Type"] = "application/json";
    delete o.json;
  }
  const r = await fetch(path, o);
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    let pesan = data?.detail ?? data;
    if (Array.isArray(pesan)) pesan = pesan.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
    throw new Error(typeof pesan === "string" ? pesan : JSON.stringify(pesan));
  }
  return data;
}

let toastTimer;
function toast(pesan, galat = false) {
  const t = $("#toast");
  t.textContent = pesan;
  t.className = "toast tampil" + (galat ? " galat" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), galat ? 6000 : 3000);
}
const gagal = (e) => toast(e.message || String(e), true);

let INFO = { gaya: ["lato"], gaya_bawaan: "lato", reframe_bawaan: true, gemini_siap: false };
let CAMPAIGNS = [];

// ------------------------------------------------------------------ job
const sudahDiumumkan = new Set();
let pollTimer;
const SELESAI_JOB = []; // callback(job) saat job selesai

function ringkasJob(j) {
  const nama = { fetch_source: "Ambil sumber", render_clips: "Render klip", auto_clips: "Klip otomatis",
                 render_ulang: "Render ulang" }[j.jenis] || j.jenis;
  const kls = { selesai: "ok", gagal: "gagal", dibatalkan: "gagal", berjalan: "jalan" }[j.status] || "";
  return { nama, kls };
}

async function pantauJob() {
  clearTimeout(pollTimer);
  let jobs = [];
  try { jobs = await api("/api/jobs"); } catch (_) { /* server restart: coba lagi */ }
  const jalan = jobs.filter((j) => j.status === "berjalan");
  $("#titik-job").className = "titik" + (jalan.length ? " jalan" : "");
  $("#label-job").textContent = jalan.length ? `${jalan.length} job berjalan` : "Job";
  $("#daftar-job").innerHTML = jobs.length ? jobs.map((j) => {
    const { nama, kls } = ringkasJob(j);
    return `<div class="job"><div class="baris renggang"><strong>${esc(nama)}</strong>
      <span class="baris"><span class="lencana ${kls}">${esc(j.status)}</span>
      <span class="redup kecil">${Math.round(j.durasi_s)} dtk</span>
      ${j.status === "berjalan" ? `<button class="ikon" data-batal="${esc(j.job_id)}" title="Batalkan">■</button>` : ""}</span></div>
      <pre>${esc(j.galat || (j.progres_terakhir || []).slice(-2).join("\n"))}</pre></div>`;
  }).join("") : `<p class="kosong">Belum ada job di sesi server ini.</p>`;
  for (const j of jobs) {
    if (j.status === "berjalan" || sudahDiumumkan.has(j.job_id)) continue;
    sudahDiumumkan.add(j.job_id);
    if (!pantauJob.awal) continue; // job lama saat halaman dibuka: jangan di-toast
    const { nama } = ringkasJob(j);
    if (j.status === "selesai") toast(`${nama} selesai`);
    else toast(`${nama} ${j.status}: ${j.galat || ""}`, true);
    const lengkap = await api(`/api/jobs/${j.job_id}`).catch(() => j);
    SELESAI_JOB.forEach((cb) => cb(lengkap));
  }
  pantauJob.awal = true;
  pollTimer = setTimeout(pantauJob, jalan.length ? 2000 : 8000);
}
const segarkanJob = () => { clearTimeout(pollTimer); pollTimer = setTimeout(pantauJob, 300); };

$("#tombol-job").onclick = () => {
  const p = $("#panel-job");
  p.hidden = !p.hidden;
  $("#tombol-job").setAttribute("aria-expanded", String(!p.hidden));
};
function tutupJob(kembali = false) {
  $("#panel-job").hidden = true;
  $("#tombol-job").setAttribute("aria-expanded", "false");
  if (kembali) $("#tombol-job").focus();
}
$("#tutup-job").onclick = () => tutupJob(true);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#panel-job").hidden) tutupJob(true); });
document.addEventListener("click", (e) => { if (!e.target.closest("#panel-job, #tombol-job")) tutupJob(); });
$("#daftar-job").onclick = async (e) => {
  const id = e.target.dataset.batal;
  if (!id) return;
  try { await api(`/api/jobs/${id}/cancel`, { method: "POST" }); toast("Membatalkan…"); segarkanJob(); }
  catch (err) { gagal(err); }
};

// --------------------------------------------------------------- router
const rute = [
  [/^#\/?$/, halamanBeranda, "beranda"],
  [/^#\/studio\/([uf]-[0-9a-f]{12})$/, halamanStudio, "beranda"],
  [/^#\/klip(?:\?.*)?$/, halamanKlip, "klip"],
  [/^#\/campaign(?:\/([a-z0-9-]+|baru))?$/, halamanCampaign, "campaign"],
  [/^#\/pengaturan$/, halamanPengaturan, "pengaturan"],
];
let bersihkan = null;
async function jalankanRute() {
  if (bersihkan) { bersihkan(); bersihkan = null; }
  SELESAI_JOB.length = 0;
  const h = location.hash || "#/";
  for (const [re, fn, nav] of rute) {
    const m = h.match(re);
    if (!m) continue;
    document.querySelectorAll("[data-nav]").forEach((a) => {
      a.classList.toggle("aktif", a.dataset.nav === nav);
      if (a.dataset.nav === nav) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    const judul = h.startsWith("#/studio/") ? "Studio editor" : { beranda: "Sumber video", klip: "Pustaka klip", campaign: "Campaign", pengaturan: "Pengaturan" }[nav];
    $("#judul-rute").textContent = judul;
    document.title = `${judul} · Clipper Studio`;
    tutupJob();
    try { await fn(...m.slice(1)); siapkanTab(); } catch (e) {
      isi.innerHTML = `<div class="kartu">${kosong("info", "Halaman belum dapat dimuat", e.message, '<button type="button" id="coba-lagi">Coba lagi</button>')}</div>`;
      $("#coba-lagi").onclick = jalankanRute;
    }
    return;
  }
  location.hash = "#/";
}
window.addEventListener("hashchange", jalankanRute);

// -------------------------------------------------------------- beranda
async function halamanBeranda() {
  isi.innerHTML = `
  <div class="halaman-kepala">
    <div><span class="eyebrow">YOUR CREATIVE WORKSPACE</span><h1>Video panjang, cerita baru.</h1>
      <p>Temukan momen terbaik. Ubah jadi klip yang siap dibagikan.</p></div>
    <a class="tombol" href="#/klip">Lihat pustaka ${ikon("arrow")}</a>
  </div>
  <div class="tumpuk">
    <section id="dasbor" class="dasbor" aria-label="Ringkasan workspace"></section>
    <div class="mulai-grid">
      <section class="kartu sumber-baru">
        <div class="judul-seksi"><span class="nomor-seksi">01</span><h2>Mulai dari satu video</h2></div>
        <p>Tempel tautan atau unggah video untuk memulai cerita berikutnya.</p>
        <div class="tab" role="tablist" aria-label="Cara menambahkan sumber">
          <button type="button" class="aktif" data-mode="url">${ikon("link")} Tautan video</button>
          <button type="button" data-mode="file">${ikon("upload")} Unggah file</button>
        </div>
        <form id="form-sumber">
          <div class="medan" data-bagian="url"><label for="url">Tautan video</label>
            <div class="input-ikon">${ikon("link")}<input id="url" type="url" placeholder="Tempel tautan YouTube atau video lainnya…" autocomplete="off"></div></div>
          <div class="medan" data-bagian="file" hidden>
            <label for="berkas" class="dropzone" id="dropzone">${ikon("upload")}<strong id="nama-berkas">Tarik video ke sini, atau pilih file</strong><small>MP4, MOV, MKV, WEBM · video asli untuk hasil terbaik</small></label>
            <input id="berkas" type="file" accept="video/*,.mp4,.mov,.mkv,.webm" aria-label="Pilih file video">
          </div>
          <div class="baris renggang sumber-submit"><span class="catatan-sumber">${ikon("info")} Transkrip dibuat otomatis setelah video ditambahkan.</span>
            <button class="utama" type="submit" id="kirim-sumber">Proses video ${ikon("arrow")}</button></div>
          <details class="opsi-sumber"><summary>Opsi transkrip</summary><div class="baris">
            <select id="bahasa" aria-label="Bahasa transkrip"><option value="">Bahasa: otomatis</option><option value="id">Indonesia</option><option value="en">Inggris</option></select>
            <label class="cek"><input id="paksa" type="checkbox"> Gunakan Whisper, abaikan subtitle bawaan</label>
          </div></details>
        </form>
      </section>
      <aside class="alur" aria-label="Alur membuat klip"><span class="eyebrow">DARI SUMBER KE LAYAR</span><h2>Tiga langkah.<br>Banyak kemungkinan.</h2>
        <div class="langkah"><span>01</span><div><strong>Tambahkan video</strong><p>Dari tautan atau rekamanmu sendiri.</p></div></div>
        <div class="langkah"><span>02</span><div><strong>Temukan momennya</strong><p>Pilih kandidat atau tandai di studio.</p></div></div>
        <div class="langkah"><span>03</span><div><strong>Buat & bagikan</strong><p>Render klip vertikal, unduh, lalu unggah.</p></div></div>
      </aside>
    </div>
    <section class="kartu">
      <div class="baris renggang sumber-kepala"><div class="judul-seksi"><h2>Video sumbermu</h2><span class="lencana" id="jumlah-sumber">…</span></div>
        <div class="sumber-aksi"><div class="input-ikon cari-sumber">${ikon("search")}<input id="cari-sumber" type="search" placeholder="Cari video sumber…" aria-label="Cari video sumber"></div>
          <button type="button" id="muat-ulang" title="Muat ulang sumber" aria-label="Muat ulang sumber">${ikon("refresh")}</button></div></div>
      <div id="daftar-sumber" class="daftar-sumber" aria-live="polite"><p class="kosong">Memuat video sumber…</p></div>
    </section>
  </div>`;

  let mode = "url";
  isi.querySelectorAll("[data-mode]").forEach((b) => b.onclick = () => {
    mode = b.dataset.mode;
    isi.querySelectorAll("[data-mode]").forEach((x) => x.classList.toggle("aktif", x === b));
    isi.querySelectorAll("[data-bagian]").forEach((x) => (x.hidden = x.dataset.bagian !== mode));
    $("#url").disabled = mode !== "url";
    $("#berkas").disabled = mode !== "file";
  });
  $("#berkas").disabled = true;
  const berkas = $("#berkas"), dropzone = $("#dropzone");
  const namaBerkas = () => { $("#nama-berkas").textContent = berkas.files[0]?.name || "Tarik video ke sini, atau pilih file"; };
  berkas.onchange = namaBerkas;
  ["dragenter", "dragover"].forEach((nama) => dropzone.addEventListener(nama, (e) => { e.preventDefault(); dropzone.classList.add("seret"); }));
  ["dragleave", "drop"].forEach((nama) => dropzone.addEventListener(nama, (e) => { e.preventDefault(); dropzone.classList.remove("seret"); }));
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files[0];
    if (!f) return;
    if (!f.type.startsWith("video/") && !/\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(f.name)) return toast("Pilih file video", true);
    const dt = new DataTransfer(); dt.items.add(f); berkas.files = dt.files; namaBerkas();
  });

  let sumber = [];
  function gambarSumber() {
    const q = $("#cari-sumber").value.trim().toLowerCase();
    const tampil = sumber.filter((x) => `${x.asal} ${namaSumber(x.asal)}`.toLowerCase().includes(q));
    $("#jumlah-sumber").textContent = sumber.length;
    $("#daftar-sumber").innerHTML = tampil.length ? tampil.map((x) => `
      <article class="sumber-row"><div class="sumber-identitas"><span class="sumber-ikon">${ikon("video")}</span><div><strong title="${esc(x.asal)}">${esc(namaSumber(x.asal))}</strong><p title="${esc(x.asal)}">${esc(x.asal)}</p><p class="sumber-ringkas">${mmss(x.durasi_s)} · ${x.jumlah_segmen} segmen</p></div></div>
        <div class="sumber-meta">${mmss(x.durasi_s)}<small>durasi video</small></div>
        <div class="sumber-meta sumber-transkrip"><span class="lencana ok">${ikon("check")} ${esc(x.transkrip_dari)}</span><small>${x.jumlah_segmen} segmen transkrip</small></div>
        <a class="tombol" href="#/studio/${esc(x.source_id)}">Buka studio ${ikon("arrow")}</a></article>`).join("")
      : kosong(q ? "search" : "video", q ? "Video belum ditemukan" : "Cerita pertamamu dimulai di sini", q ? "Coba kata kunci atau tautan lainnya." : "Tambahkan tautan atau unggah video di atas untuk mulai membuat klip.");
  }
  $("#cari-sumber").oninput = gambarSumber;
  async function muat() {
    sumber = await api("/api/sources");
    if ($("#daftar-sumber")) gambarSumber();
  }
  async function dasbor() {
    const r = await api("/api/ringkasan");
    if (!$("#dasbor")) return;
    const ubin = (angka, label, href, simbol, ket = "") =>
      `<a class="ubin" href="${href}"><div class="ubin-kepala"><span>${esc(label)}</span>${ikon(simbol)}</div><strong>${esc(angka)}</strong><small>${esc(ket)}</small></a>`;
    $("#dasbor").innerHTML = [
      ubin(r.sumber, "Video sumber", "#/", "video", "awal setiap cerita"),
      ubin(r.klip, "Total klip", "#/klip", "grid", `${r.klip_mb} MB tersimpan`),
      ubin(r.per_status.baru, "Belum diunggah", "#/klip?status=baru", "scissors", "siap langkah berikutnya"),
      ubin(r.per_status.diunggah, "Diunggah", "#/klip?status=diunggah", "upload", "sudah dibagikan"),
      ubin(r.per_status.disubmit, "Disubmit", "#/klip?status=disubmit", "check", "terkirim ke campaign"),
      ubin(r.job_berjalan, "Job berjalan", "#/", "activity", r.disk ? `${r.disk.kosong_gb} GB tersedia` : "proses di studio"),
    ].join("");
  }
  $("#muat-ulang").onclick = async () => {
    const b = $("#muat-ulang"); b.disabled = true;
    try { await Promise.all([muat(), dasbor()]); } catch (err) { gagal(err); } finally { b.disabled = false; }
  };
  muat().catch(gagal);
  dasbor().catch(() => {});

  SELESAI_JOB.push((j) => {
    dasbor().catch(() => {});
    if (j.jenis !== "fetch_source") return;
    muat().catch(() => {});
    if (j.status === "selesai" && j.hasil?.source_id) location.hash = `#/studio/${j.hasil.source_id}`;
  });

  $("#form-sumber").onsubmit = async (e) => {
    e.preventDefault();
    const tombol = $("#kirim-sumber");
    tombol.disabled = true;
    try {
      let j;
      if (mode === "url") {
        const url = $("#url").value.trim();
        if (!url) throw new Error("Isi URL dulu");
        j = await api("/api/sources", { method: "POST", json: { sumber: url, bahasa: $("#bahasa").value || null, paksa_whisper: $("#paksa").checked } });
      } else {
        const f = $("#berkas").files[0];
        if (!f) throw new Error("Pilih file dulu");
        const fd = new FormData();
        fd.append("file", f);
        fd.append("bahasa", $("#bahasa").value);
        fd.append("paksa_whisper", $("#paksa").checked ? "true" : "false");
        toast("Mengunggah…");
        j = await api("/api/sources/upload", { method: "POST", body: fd });
      }
      if (j.status === "selesai" && j.hasil?.source_id) { location.hash = `#/studio/${j.hasil.source_id}`; return; }
      toast("Sumber sedang diambil — pantau di panel Job");
      segarkanJob();
    } catch (err) { gagal(err); } finally { tombol.disabled = false; }
  };
}

// --------------------------------------------------------------- studio
async function halamanStudio(sid) {
  const [meta, tr] = await Promise.all([api(`/api/sources/${sid}`), api(`/api/sources/${sid}/transcript`)]);
  const kunciPilihan = `pilihan:${sid}`;
  let pilihan = bacaLokal(kunciPilihan, []);
  const camps = CAMPAIGNS.filter((c) => c.slug);   // brief rusak tidak bisa dipakai render
  let campaign = bacaLokal("campaign-terakhir", camps[0]?.slug || "");
  if (!camps.some((c) => c.slug === campaign)) campaign = camps[0]?.slug || "";
  let batasAkhir = null; // pratinjau berhenti di sini
  let tanda = { awal: null, akhir: null };

  isi.innerHTML = `
  <a class="breadcrumb" href="#/">${ikon("back")} Kembali ke sumber video</a>
  <div class="halaman-kepala studio-kepala">
    <div><span class="eyebrow">STUDIO EDITOR</span><h1 title="${esc(meta.asal)}">${esc(namaSumber(meta.asal))}</h1>
      <span class="redup kecil">${mmss(meta.durasi_s)} · transkrip ${esc(meta.transkrip_dari)} · ${meta.jumlah_segmen} segmen</span></div>
    <div class="baris"><label for="campaign" style="margin:0">Campaign</label>
      <select id="campaign">${camps.map((c) => `<option value="${esc(c.slug)}">${esc(c.nama || c.slug)}</option>`).join("")}</select></div>
  </div>
  <div class="studio">
    <div class="tumpuk">
      <section class="kartu pemutar">
        <video id="video" controls preload="metadata" src="/media/source/${esc(sid)}"></video>
        <div class="baris renggang kontrol-waktu">
          <div class="baris">
            <button type="button" id="tanda-awal">Tandai awal</button>
            <button type="button" id="tanda-akhir">Tandai akhir</button>
            <span id="info-tanda" class="redup kecil"></span>
          </div>
          <button type="button" id="tambah-tanda" disabled>+ Jadikan pilihan</button>
        </div>
      </section>
      <section class="kartu">
        <div class="tab" role="tablist" aria-label="Momen dan transkrip">
          <button type="button" class="aktif" data-tab="kandidat">Kandidat</button>
          <button type="button" data-tab="transkrip">Transkrip</button>
        </div>
        <div data-isi="kandidat">
          <div class="baris renggang" style="margin-bottom:.5rem">
            <span id="info-kandidat" class="redup kecil"></span>
            <select id="urut" aria-label="Urutkan"><option value="skor">Urut: skor kata kunci</option><option value="waktu">Urut: waktu</option></select>
          </div>
          <div id="daftar-kandidat" class="daftar-gulir"></div>
        </div>
        <div data-isi="transkrip" hidden>
          <input id="cari" type="search" placeholder="Cari di transkrip…" aria-label="Cari di transkrip" style="width:100%;margin-bottom:.5rem">
          <div id="daftar-transkrip" class="daftar-gulir" tabindex="0" role="region" aria-label="Transkrip video"></div>
        </div>
      </section>
    </div>
    <div class="tumpuk">
      <section class="kartu">
        <div class="baris renggang"><h2>Pilihan (<span id="jumlah-pilihan">0</span>)</h2>
          <button type="button" id="kosongkan" class="ikon" title="Hapus semua">Kosongkan</button></div>
        <p class="redup kecil" style="margin-top:-.4rem">Saat render, waktu otomatis ditempel ke kalimat utuh dalam batas durasi.</p>
        <div id="daftar-pilihan"></div>
        <div class="grid-form">
          <div class="medan"><label for="gaya">Gaya subtitle</label><select id="gaya">${INFO.gaya.map((g) => `<option ${g === INFO.gaya_bawaan ? "selected" : ""}>${esc(g)}</option>`).join("")}</select></div>
          <div class="medan"><label for="maks">Durasi maks (dtk)</label><input id="maks" type="number" min="5" step="1"></div>
        </div>
        <label class="cek medan"><input id="reframe" type="checkbox" ${INFO.reframe_bawaan ? "checked" : ""}> Reframe ikut wajah (blur-pad bila tak ada / banyak wajah)</label>
        <p id="info-maks" class="redup kecil"></p>
        <button type="button" class="utama" id="render" style="width:100%">Render pilihan</button>
      </section>
      <section class="kartu">
        <h2>Klip otomatis</h2>
        <p class="redup kecil" style="margin-top:-.4rem">Engine yang memilih momen, tanpa review.</p>
        <div class="baris">
          <input id="jumlah-auto" type="number" min="1" max="20" value="3" style="width:5rem" aria-label="Jumlah klip">
          <select id="ai-auto" aria-label="Pemilih"><option value="keyword">Kata kunci</option>
            <option value="gemini" ${INFO.gemini_siap ? "" : "disabled"}>Gemini${INFO.gemini_siap ? "" : " (API key belum diatur)"}</option></select>
          <button type="button" id="auto">Buat</button>
        </div>
      </section>
    </div>
  </div>`;

  const video = $("#video");
  const pilihCampaign = $("#campaign");
  pilihCampaign.value = campaign;

  // --- batas durasi campaign
  function campaignKini() { return camps.find((c) => c.slug === campaign); }
  function aturMaks() {
    const c = campaignKini();
    const maksC = c?.durasi_s?.[1] ?? 60;
    const m = $("#maks");
    m.max = String(maksC);
    const bawaan = INFO.maks_durasi_bawaan || 60;
    m.value = String(Math.min(maksC, bawaan));
    $("#info-maks").textContent = c ? `Campaign mengizinkan ${c.durasi_s[0]}–${maksC} dtk. Bawaan ${bawaan} dtk (atur di Pengaturan); naikkan bila perlu.` : "";
  }
  aturMaks();

  // --- pemutar & pratinjau
  function putar(a, b) {
    batasAkhir = b ?? null;
    video.currentTime = a;
    video.play().catch(() => {});
  }
  let baris = [];
  video.addEventListener("timeupdate", () => {
    if (batasAkhir !== null && video.currentTime >= batasAkhir) { video.pause(); batasAkhir = null; }
    const t = video.currentTime;
    const i = tr.segmen.findIndex((s) => s[0] <= t && t < s[1]);
    baris.forEach((el) => el.classList.toggle("kini", Number(el.dataset.i) === i));
  });
  video.addEventListener("seeking", () => { if (batasAkhir !== null && video.currentTime > batasAkhir) batasAkhir = null; });

  function infoTanda() {
    $("#info-tanda").textContent = tanda.awal === null && tanda.akhir === null ? "" :
      `${tanda.awal === null ? "—" : mmss(tanda.awal)} → ${tanda.akhir === null ? "—" : mmss(tanda.akhir)}`;
    $("#tambah-tanda").disabled = !(tanda.awal !== null && tanda.akhir !== null && tanda.akhir > tanda.awal);
  }
  $("#tanda-awal").onclick = () => { tanda.awal = +video.currentTime.toFixed(1); infoTanda(); };
  $("#tanda-akhir").onclick = () => { tanda.akhir = +video.currentTime.toFixed(1); infoTanda(); };
  $("#tambah-tanda").onclick = () => { tambahPilihan(tanda.awal, tanda.akhir, teksAntara(tanda.awal, tanda.akhir)); tanda = { awal: null, akhir: null }; infoTanda(); };

  function teksAntara(a, b) {
    return tr.segmen.filter((s) => s[1] > a && s[0] < b).map((s) => s[2]).join(" ");
  }

  // --- tab
  isi.querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => {
    isi.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("aktif", x === b));
    isi.querySelectorAll("[data-isi]").forEach((x) => (x.hidden = x.dataset.isi !== b.dataset.tab));
  });

  // --- transkrip
  function gambarTranskrip() {
    const q = $("#cari").value.trim().toLowerCase();
    const el = $("#daftar-transkrip");
    const tampil = tr.segmen.map((s, i) => [s, i]).filter(([s]) => !q || s[2].toLowerCase().includes(q));
    el.innerHTML = tampil.length ? tampil.slice(0, 3000).map(([s, i]) =>
      `<div class="baris-transkrip" data-i="${i}" data-t="${s[0]}"><time>${mmss(s[0])}</time><span>${esc(s[2])}</span></div>`).join("")
      : `<p class="kosong">Tidak ada yang cocok.</p>`;
    baris = [...el.querySelectorAll(".baris-transkrip")];
  }
  $("#cari").oninput = gambarTranskrip;
  $("#daftar-transkrip").onclick = (e) => {
    const b = e.target.closest(".baris-transkrip");
    if (b) putar(Number(b.dataset.t));
  };
  gambarTranskrip();

  // --- kandidat
  let kandidat = [];
  async function muatKandidat() {
    if (!campaign) { $("#daftar-kandidat").innerHTML = `<p class="kosong">Buat campaign dulu di menu Campaign.</p>`; return; }
    const r = await api(`/api/sources/${sid}/candidates?campaign=${encodeURIComponent(campaign)}&urut=${$("#urut").value}&maks_durasi=${encodeURIComponent($("#maks").value || 60)}`);
    kandidat = r.kandidat;
    $("#info-kandidat").textContent = `${r.total} potongan ${r.durasi_s[0]}–${r.durasi_s[1]} dtk, mulai di awal kalimat`;
    $("#daftar-kandidat").innerHTML = kandidat.length ? kandidat.map((k, i) => `
      <div class="kandidat" data-i="${i}">
        <div class="baris renggang"><strong>${esc(k.rentang)}</strong>
          <span class="baris">${k.akhir_kalimat === false ? `<span class="lencana jalan" title="Kalimat terakhir lebih panjang dari batas durasi; geser akhir atau naikkan durasi maks">berhenti di tengah kalimat</span>` : ""}
          <span class="lencana">${k.durasi} dtk</span>${k.skor_kata_kunci ? `<span class="lencana ok">skor ${k.skor_kata_kunci}</span>` : ""}</span></div>
        <p>${esc(k.teks)}</p>
        <div class="baris"><button type="button" data-aksi="putar">▶ Pratinjau</button>
          <button type="button" data-aksi="pilih">+ Pilih</button>
          <button type="button" data-aksi="buka" class="ikon">Teks lengkap</button></div>
      </div>`).join("") : `<p class="kosong">Tidak ada potongan yang muat dalam batas durasi.</p>`;
  }
  $("#daftar-kandidat").onclick = (e) => {
    const aksi = e.target.dataset.aksi;
    const kartu = e.target.closest(".kandidat");
    if (!aksi || !kartu) return;
    const k = kandidat[Number(kartu.dataset.i)];
    if (aksi === "putar") putar(k.start, k.end);
    if (aksi === "pilih") tambahPilihan(k.start, k.end, k.teks);
    if (aksi === "buka") kartu.classList.toggle("terbuka");
  };
  $("#urut").onchange = () => muatKandidat().catch(gagal);
  $("#maks").onchange = () => muatKandidat().catch(gagal);
  pilihCampaign.onchange = () => {
    campaign = pilihCampaign.value;
    simpanLokal("campaign-terakhir", campaign);
    aturMaks();
    muatKandidat().catch(gagal);
  };
  muatKandidat().catch(gagal);

  // --- pilihan
  function simpan() { simpanLokal(kunciPilihan, pilihan); }
  function tambahPilihan(start, end, teks) {
    if (pilihan.some((p) => Math.abs(p.start - start) < 0.5 && Math.abs(p.end - end) < 0.5)) { toast("Sudah ada di pilihan"); return; }
    pilihan.push({ start: +(+start).toFixed(1), end: +(+end).toFixed(1), hook_title: "", teks: (teks || "").slice(0, 400) });
    simpan(); gambarPilihan();
    toast("Ditambahkan ke pilihan — tulis hook-nya");
  }
  function gambarPilihan() {
    $("#jumlah-pilihan").textContent = pilihan.length;
    $("#daftar-pilihan").innerHTML = pilihan.length ? pilihan.map((p, i) => `
      <div class="pilihan" data-i="${i}">
        <div class="baris renggang"><strong>${mmss(p.start)} → ${mmss(p.end)}</strong>
          <span class="baris"><span class="lencana">${(p.end - p.start).toFixed(1)} dtk</span>
          <button type="button" class="ikon" data-aksi="putar" title="Pratinjau">▶</button>
          <button type="button" class="ikon" data-aksi="hapus" title="Hapus">✕</button></span></div>
        <div class="waktu">
          <div><label>Awal (dtk)</label><input type="number" step="0.1" min="0" data-f="start" aria-label="Waktu awal klip dalam detik" value="${p.start}">
            <div class="geser"><button type="button" data-geser="start:-1">−1</button><button type="button" data-geser="start:1">+1</button></div></div>
          <div><label>Akhir (dtk)</label><input type="number" step="0.1" min="0" data-f="end" aria-label="Waktu akhir klip dalam detik" value="${p.end}">
            <div class="geser"><button type="button" data-geser="end:-1">−1</button><button type="button" data-geser="end:1">+1</button></div></div>
        </div>
        <label>Hook / judul (masuk caption)</label>
        <input type="text" data-f="hook_title" maxlength="200" value="${esc(p.hook_title)}" placeholder="Hook jujur — kosong = ambil dari kalimat pembuka" style="width:100%">
        ${p.teks ? `<p class="redup kecil" style="margin:.4rem 0 0">${esc(p.teks.slice(0, 160))}${p.teks.length > 160 ? "…" : ""}</p>` : ""}
      </div>`).join("") : `<p class="kosong">Pilih potongan dari Kandidat, atau tandai awal/akhir di pemutar.</p>`;
  }
  const daftarPilihan = $("#daftar-pilihan");
  daftarPilihan.oninput = (e) => {
    const f = e.target.dataset.f;
    const kartu = e.target.closest(".pilihan");
    if (!f || !kartu) return;
    const p = pilihan[Number(kartu.dataset.i)];
    p[f] = f === "hook_title" ? e.target.value : Number(e.target.value);
    simpan();
  };
  daftarPilihan.onchange = (e) => { if (e.target.dataset.f === "start" || e.target.dataset.f === "end") gambarPilihan(); };
  daftarPilihan.onclick = (e) => {
    const kartu = e.target.closest(".pilihan");
    if (!kartu) return;
    const i = Number(kartu.dataset.i);
    const p = pilihan[i];
    if (e.target.dataset.aksi === "putar") putar(p.start, p.end);
    if (e.target.dataset.aksi === "hapus") { pilihan.splice(i, 1); simpan(); gambarPilihan(); }
    if (e.target.dataset.geser) {
      const [f, d] = e.target.dataset.geser.split(":");
      p[f] = Math.max(0, +(p[f] + Number(d)).toFixed(1));
      simpan(); gambarPilihan();
      putar(f === "start" ? p.start : Math.max(0, p.end - 3), p.end);
    }
  };
  $("#kosongkan").onclick = () => {
    if (pilihan.length && confirm("Hapus semua pilihan?")) { pilihan = []; simpan(); gambarPilihan(); }
  };
  gambarPilihan();

  // --- render & auto
  const opsi = () => ({ gaya: $("#gaya").value, reframe: $("#reframe").checked, maks_durasi: Number($("#maks").value) || 60 });
  $("#render").onclick = async () => {
    if (!campaign) return toast("Pilih campaign dulu", true);
    if (!pilihan.length) return toast("Belum ada pilihan", true);
    const salah = pilihan.find((p) => !(p.end > p.start));
    if (salah) return toast(`Pilihan ${mmss(salah.start)}: akhir harus setelah awal`, true);
    try {
      await api("/api/render", { method: "POST", json: { source_id: sid, campaign, ...opsi(),
        pilihan: pilihan.map(({ start, end, hook_title }) => ({ start, end, hook_title })) } });
      toast(`Render ${pilihan.length} klip dimulai — pantau di panel Job`);
      segarkanJob();
    } catch (err) { gagal(err); }
  };
  $("#auto").onclick = async () => {
    if (!campaign) return toast("Pilih campaign dulu", true);
    try {
      await api("/api/auto", { method: "POST", json: { source_id: sid, campaign, ...opsi(),
        jumlah: Number($("#jumlah-auto").value) || 3, ai: $("#ai-auto").value } });
      toast("Klip otomatis dimulai — pantau di panel Job");
      segarkanJob();
    } catch (err) { gagal(err); }
  };
  SELESAI_JOB.push((j) => {
    if ((j.jenis === "render_clips" || j.jenis === "auto_clips") && j.status === "selesai") {
      const n = j.hasil?.klip?.length ?? 0;
      const lewat = j.hasil?.dilewati?.length ? `, ${j.hasil.dilewati.length} dilewati` : "";
      toast(`${n} klip jadi${lewat} — lihat di Pustaka klip`);
    }
  });
  bersihkan = () => video.pause();
}

// ---------------------------------------------------------------- klip
const LABEL_STATUS = { baru: "Baru", diunggah: "Diunggah", disubmit: "Disubmit" };
const klipUrl = (k) => `${encodeURIComponent(k.campaign)}/${encodeURIComponent(k.source_id)}/${encodeURIComponent(k.file)}`;

async function halamanKlip() {
  const filter = bacaLokal("filter-klip", "");
  const dariTautan = new URLSearchParams(location.hash.split("?")[1] || "").get("status");
  const filterStatus = dariTautan ?? bacaLokal("filter-status", "");
  isi.innerHTML = `
  <div class="halaman-kepala"><div><span class="eyebrow">KOLEKSI KONTENMU</span><h1>Pustaka klip</h1>
    <p>Momen pilihanmu, dalam satu tempat. Pratinjau, atur caption, lalu bagikan.</p></div>
    <a class="tombol utama" href="#/">${ikon("upload")} Tambah video</a></div>
  <div class="toolbar-klip"><div class="input-ikon">${ikon("search")}<input id="cari-klip" type="search" placeholder="Cari hook, nama klip, atau campaign…" aria-label="Cari klip"></div><span id="jumlah-klip">Memuat…</span>
    <select id="filter" aria-label="Filter campaign"><option value="">Semua campaign</option>
      ${CAMPAIGNS.filter((c) => c.slug).map((c) => `<option value="${esc(c.slug)}" ${c.slug === filter ? "selected" : ""}>${esc(c.nama || c.slug)}</option>`).join("")}</select>
    <select id="filter-status" aria-label="Filter status"><option value="">Semua status</option>
      ${Object.entries(LABEL_STATUS).map(([k, v]) => `<option value="${k}" ${k === filterStatus ? "selected" : ""}>${v}</option>`).join("")}</select>
  </div>
  <div id="grid" class="grid-klip"></div>
  <p class="catatan-sumber" style="margin-top:20px">${ikon("info")} Unduh klip dan unggah manual ke platform pilihanmu. Hook dapat diubah tanpa render ulang.</p>`;

  let klip = [], semuaKlip = [];
  function gambarKlip() {
    const q = $("#cari-klip").value.trim().toLowerCase(), st = $("#filter-status").value;
    klip = semuaKlip.filter((k) => (!st || k.status === st) && `${k.hook || ""} ${k.file} ${k.campaign}`.toLowerCase().includes(q));
    $("#jumlah-klip").textContent = `${klip.length} klip`;
    const terfilter = q || $("#filter").value || st;
    $("#grid").innerHTML = klip.length ? klip.map((k, i) => kartuKlip(k, i)).join("")
      : kosong(terfilter ? "search" : "scissors", terfilter ? "Belum ada klip yang cocok" : "Pustakamu siap diisi", terfilter ? "Coba kata kunci lain atau ubah filter campaign dan status." : "Pilih momen di studio, lalu render klip pertamamu.", terfilter ? '<button type="button" id="reset-filter">Hapus filter</button>' : '<a class="tombol utama" href="#/">Tambah video</a>');
    if ($("#reset-filter")) $("#reset-filter").onclick = () => {
      $("#cari-klip").value = ""; $("#filter").value = ""; $("#filter-status").value = "";
      simpanLokal("filter-klip", ""); simpanLokal("filter-status", "");
      muat().catch(gagal);
    };
  }
  async function muat() {
    const f = $("#filter").value;
    semuaKlip = await api(`/api/clips${f ? `?campaign=${encodeURIComponent(f)}` : ""}`);
    if ($("#grid")) gambarKlip();
  }
  $("#cari-klip").oninput = gambarKlip;

  function kartuKlip(k, i) {
    const u = klipUrl(k);
    return `<article class="kartu klip" data-i="${i}">
      <button type="button" class="sampul" data-aksi="putar" aria-label="Putar ${esc(k.file)}">
        <img loading="lazy" src="/media/thumb/${u}?v=${k.dibuat}" alt=""><span class="tombol-putar">▶</span></button>
      <div class="baris renggang" style="margin-top:.5rem">
        <select data-aksi="status" class="status-${esc(k.status)}" aria-label="Status">${Object.entries(LABEL_STATUS).map(([s, l]) => `<option value="${s}" ${s === k.status ? "selected" : ""}>${l}</option>`).join("")}</select>
        <span class="redup kecil">${Number(k.durasi || 0).toFixed(1)} dtk · ${k.ukuran_mb} MB</span></div>
      <h3 data-hook>${esc(k.hook || k.file)}</h3>
      <div class="redup kecil">${esc(k.campaign)} · ${esc(k.file)}${k.gaya ? ` · gaya ${esc(k.gaya)}` : ""}</div>
      ${k.tautan ? `<div class="kecil potong"><a href="${esc(k.tautan)}" target="_blank" rel="noopener noreferrer">${esc(k.tautan)}</a></div>` : ""}
      <div class="baris aksi-klip">
        <a class="tombol" href="/media/clip/${u}?unduh=true">Unduh</a>
        <button type="button" data-aksi="caption">Caption</button>
        <button type="button" data-aksi="edit">Edit</button>
        <button type="button" data-aksi="ulang">Render ulang</button>
        <button type="button" class="ikon bahaya" data-aksi="hapus" title="Hapus klip">Hapus</button>
      </div>
      <div class="panel-klip" hidden></div>
    </article>`;
  }

  async function buka(kartu, jenis, k) {
    const p = kartu.querySelector(".panel-klip");
    if (!p.hidden && p.dataset.jenis === jenis) { p.hidden = true; return; }
    p.dataset.jenis = jenis;
    if (jenis === "caption") {
      const d = await api(`/api/clips/${klipUrl(k)}`);
      p._varian = d.varian_platform;
      p.innerHTML = d.varian_platform.map((x, j) => `<div><div class="baris renggang"><strong>${esc(x.platform)}</strong>
        <button type="button" class="ikon" data-salin="${j}">Salin</button></div>
        <pre>${esc(x.caption)}</pre><div class="redup kecil">maks ${x.maks_durasi} dtk · ${esc(x.catatan)}</div></div>`).join("") || "<p class='redup'>Tidak ada caption.</p>";
    } else if (jenis === "edit") {
      p.innerHTML = `<label>Hook (baris pertama caption)</label><textarea rows="3" maxlength="500" data-f="hook" aria-label="Hook klip">${esc(k.hook || "")}</textarea>
        <label style="margin-top:.5rem">Tautan postingan</label><input type="url" data-f="tautan" value="${esc(k.tautan || "")}" placeholder="https://www.tiktok.com/@akun/video/…" style="width:100%">
        <div class="baris" style="margin-top:.5rem"><button type="button" class="utama" data-aksi="simpan-edit">Simpan</button></div>`;
    } else if (jenis === "ulang") {
      p.innerHTML = `<div class="grid-form">
        <div class="medan"><label>Gaya subtitle</label><select data-f="gaya" aria-label="Gaya subtitle untuk render ulang">${INFO.gaya.map((g) => `<option ${g === (INFO.gaya.includes(k.gaya) ? k.gaya : INFO.gaya_bawaan) ? "selected" : ""}>${esc(g)}</option>`).join("")}</select></div></div>
        <label class="cek medan"><input type="checkbox" data-f="reframe" ${INFO.reframe_bawaan ? "checked" : ""}> Reframe ikut wajah</label>
        <p class="redup kecil">Menimpa ${esc(k.file)}; status & tautan dipertahankan. Kualitas/encode mengikuti Pengaturan saat ini.</p>
        <button type="button" class="utama" data-aksi="mulai-ulang">Render ulang</button>`;
    }
    p.hidden = false;
  }

  $("#grid").onclick = async (e) => {
    const kartu = e.target.closest(".klip");
    if (!kartu) return;
    const k = klip[Number(kartu.dataset.i)];
    const aksi = e.target.closest("[data-aksi]")?.dataset.aksi;
    const p = kartu.querySelector(".panel-klip");
    try {
      if (aksi === "putar") {
        const v = document.createElement("video");
        v.src = `/media/clip/${klipUrl(k)}`; v.controls = true; v.autoplay = true; v.playsInline = true;
        kartu.querySelector(".sampul").replaceWith(v);
      } else if (["caption", "edit", "ulang"].includes(aksi)) {
        await buka(kartu, aksi, k);
      } else if (aksi === "simpan-edit") {
        const d = await api(`/api/clips/${klipUrl(k)}`, { method: "PATCH", json: {
          hook: p.querySelector("[data-f=hook]").value, tautan: p.querySelector("[data-f=tautan]").value } });
        Object.assign(k, { hook: d.hook, tautan: d.tautan || "" });
        kartu.outerHTML = kartuKlip(k, Number(kartu.dataset.i));
        toast("Hook & caption diperbarui");
      } else if (aksi === "mulai-ulang") {
        await api(`/api/clips/${klipUrl(k)}/render-ulang`, { method: "POST", json: {
          gaya: p.querySelector("[data-f=gaya]").value, reframe: p.querySelector("[data-f=reframe]").checked } });
        p.hidden = true;
        toast(`Render ulang ${k.file} dimulai — pantau di panel Job`);
        segarkanJob();
      } else if (aksi === "hapus") {
        if (!confirm(`Hapus ${k.file} beserta subtitle & caption-nya? Tidak bisa dibatalkan.`)) return;
        await api(`/api/clips/${klipUrl(k)}`, { method: "DELETE" });
        toast(`${k.file} dihapus`);
        muat();
      }
      if (e.target.dataset.salin !== undefined) {
        try { await navigator.clipboard.writeText(p._varian[Number(e.target.dataset.salin)].caption); toast("Caption disalin"); }
        catch (_) { toast("Gagal menyalin — pilih teksnya manual", true); }
      }
    } catch (err) { gagal(err); }
  };
  $("#grid").onchange = async (e) => {
    if (e.target.dataset.aksi !== "status") return;
    const kartu = e.target.closest(".klip");
    const k = klip[Number(kartu.dataset.i)];
    try {
      await api(`/api/clips/${klipUrl(k)}`, { method: "PATCH", json: { status: e.target.value } });
      k.status = e.target.value;
      e.target.className = `status-${k.status}`;
      if ($("#filter-status").value) gambarKlip();
      toast(`Status: ${LABEL_STATUS[k.status]}`);
    } catch (err) { gagal(err); e.target.value = k.status; }
  };
  $("#filter").onchange = () => { simpanLokal("filter-klip", $("#filter").value); muat().catch(gagal); };
  $("#filter-status").onchange = () => { simpanLokal("filter-status", $("#filter-status").value); gambarKlip(); };
  SELESAI_JOB.push((j) => { if (j.jenis !== "fetch_source") muat().catch(() => {}); });
  await muat();
}

// ------------------------------------------------------------ campaign
const DAFTAR = ["platform", "hashtag", "keywords"];   // dipisah koma
const BARIS = ["angle", "larangan"];                 // satu per baris

async function halamanCampaign(slug) {
  CAMPAIGNS = await api("/api/campaigns");
  const pertama = CAMPAIGNS.find((c) => c.slug);
  if (!slug && pertama) { location.hash = `#/campaign/${pertama.slug}`; return; }
  const baru = slug === "baru" || !slug;
  let brief = baru || !slug ? { slug: "", nama: "", cpm_rp: 0, durasi_min_s: 15, durasi_maks_s: 60, platform: ["TikTok", "Instagram"], hashtag: [] }
    : await api(`/api/campaigns/${slug}`);

  isi.innerHTML = `
  <div class="halaman-kepala"><div><span class="eyebrow">ARAH UNTUK SETIAP CERITA</span><h1>Campaign</h1><p>Atur brief, kata kunci, dan aturan konten sebelum mulai membuat klip.</p></div>
    <a class="tombol" href="#/campaign/baru">+ Campaign baru</a></div>
  <div class="dua-kolom">
    <section class="kartu daftar-campaign">
      ${CAMPAIGNS.map((c) => c.slug ? `<a href="#/campaign/${esc(c.slug)}" class="${c.slug === slug ? "aktif" : ""}">${esc(c.nama || c.slug)}<br><span class="redup kecil">${esc(c.slug)}</span></a>`
        : `<div class="redup kecil">${esc(c.file)}: ${esc(c.error)}</div>`).join("")}
      <a href="#/campaign/baru" class="${baru ? "aktif" : ""}">+ Campaign baru</a>
    </section>
    <form class="kartu" id="form-campaign">
      <h2>${baru ? "Campaign baru" : esc(brief.nama || brief.slug)}</h2>
      <div class="grid-form">
        <div class="medan"><label for="f-slug">Slug (huruf kecil, angka, -)</label><input id="f-slug" name="slug" required pattern="[a-z0-9][a-z0-9-]{0,63}" ${baru ? "" : "readonly"}></div>
        <div class="medan"><label for="f-nama">Nama</label><input id="f-nama" name="nama" required></div>
        <div class="medan"><label for="f-sp">Sumber platform</label><input id="f-sp" name="sumber_platform" placeholder="Clippo"></div>
        <div class="medan"><label for="f-cpm">CPM (Rp / 1.000 view)</label><input id="f-cpm" name="cpm_rp" type="number" min="0" required></div>
        <div class="medan"><label for="f-min">Durasi min (dtk)</label><input id="f-min" name="durasi_min_s" type="number" min="1" step="1" required></div>
        <div class="medan"><label for="f-maks">Durasi maks (dtk)</label><input id="f-maks" name="durasi_maks_s" type="number" min="2" step="1" required></div>
      </div>
      <div class="medan"><label for="f-platform">Platform (pisahkan koma)</label><input id="f-platform" name="platform" required></div>
      <div class="medan"><label for="f-hashtag">Hashtag wajib (pisahkan koma atau spasi)</label><input id="f-hashtag" name="hashtag" required></div>
      <div class="medan"><label for="f-kw">Kata kunci (pisahkan koma)</label><input id="f-kw" name="keywords"></div>
      <div class="medan"><label for="f-angle">Angle (satu per baris)</label><textarea id="f-angle" name="angle" rows="3"></textarea></div>
      <div class="medan"><label for="f-larangan">Larangan (satu per baris)</label><textarea id="f-larangan" name="larangan" rows="4"></textarea></div>
      <div class="medan"><label for="f-koreksi">Koreksi transkrip (JSON: "salah": "benar")</label><textarea id="f-koreksi" name="koreksi" rows="5" spellcheck="false"></textarea></div>
      <button type="submit" class="utama">Simpan</button>
    </form>
  </div>`;

  const f = $("#form-campaign");
  for (const el of f.elements) {
    if (!el.name) continue;
    const v = brief[el.name];
    if (DAFTAR.includes(el.name)) el.value = (v || []).join(el.name === "hashtag" ? " " : ", ");
    else if (BARIS.includes(el.name)) el.value = (v || []).join("\n");
    else if (el.name === "koreksi") el.value = JSON.stringify(v || {}, null, 2);
    else el.value = v ?? "";
  }
  f.onsubmit = async (e) => {
    e.preventDefault();
    const hasil = { ...brief };   // pertahankan field lain yang tidak ada di form
    try {
      for (const el of f.elements) {
        if (!el.name) continue;
        const v = el.value.trim();
        if (DAFTAR.includes(el.name)) hasil[el.name] = v.split(el.name === "hashtag" ? /[\s,]+/ : /\s*,\s*/).filter(Boolean);
        else if (BARIS.includes(el.name)) hasil[el.name] = v.split("\n").map((x) => x.trim()).filter(Boolean);
        else if (el.name === "koreksi") {
          try { hasil.koreksi = v ? JSON.parse(v) : {}; } catch (_) { throw new Error("Koreksi bukan JSON yang sah"); }
        } else if (el.type === "number") hasil[el.name] = Number(v);
        else hasil[el.name] = v;
      }
      if (!hasil.sumber_platform) delete hasil.sumber_platform;
      hasil.hashtag = hasil.hashtag.map((h) => (h.startsWith("#") ? h : `#${h}`));
      if (baru) await api("/api/campaigns", { method: "POST", json: hasil });
      else await api(`/api/campaigns/${hasil.slug}`, { method: "PUT", json: hasil });
      toast("Campaign disimpan");
      CAMPAIGNS = await api("/api/campaigns");
      location.hash = `#/campaign/${hasil.slug}`;
      if (!baru) halamanCampaign(hasil.slug);
    } catch (err) { gagal(err); }
  };
}

// ----------------------------------------------------------- pengaturan
function inputDariSkema(nama, a, nilai, opsi = {}) {
  const id = `s-${nama}`;
  const mati = opsi.terkunci ? "disabled" : "";
  const atr = (x) => (x === undefined ? "" : x);
  if (a.tipe === "boolean")
    return `<label class="cek"><input type="checkbox" id="${id}" data-k="${esc(nama)}" ${nilai ? "checked" : ""} ${mati}> ${esc(a.label)}</label>`;
  let el;
  if (a.tipe === "pilihan") {
    const lab = a.label_pilihan || {};
    el = `<select id="${id}" data-k="${esc(nama)}" ${mati}>${a.pilihan.map((p) => {
      const v = p === null ? "" : String(p);
      return `<option value="${esc(v)}" ${String(nilai ?? "") === v ? "selected" : ""}>${esc(lab[v] ?? v)}</option>`;
    }).join("")}</select>`;
  } else if (a.tipe === "gaya") {
    el = `<select id="${id}" data-k="${esc(nama)}" ${mati}>${(opsi.gaya || []).map((g) =>
      `<option ${g === nilai ? "selected" : ""}>${esc(g)}</option>`).join("")}</select>`;
  } else if (a.tipe === "angka" || a.tipe === "bulat") {
    el = `<input id="${id}" data-k="${esc(nama)}" type="number" value="${esc(nilai)}" min="${atr(a.min)}" max="${atr(a.maks)}" step="${a.langkah ?? (a.tipe === "bulat" ? 1 : "any")}" ${mati}>`;
  } else if (a.tipe === "warna") {
    el = `<input id="${id}" data-k="${esc(nama)}" type="color" value="${esc(nilai)}" ${mati}>`;
  } else if (a.tipe === "rahasia") {
    const ada = nilai && nilai.ada;
    el = `<div class="baris"><span class="lencana ${ada ? "ok" : ""}">${ada ? `tersimpan …${esc(nilai.akhir)}` : "belum diatur"}</span>
      <input id="${id}" data-k="${esc(nama)}" type="password" autocomplete="off" placeholder="${ada ? "tempel key baru untuk mengganti" : "tempel API key"}" style="flex:1" ${mati}>
      ${ada && !opsi.terkunci ? `<button type="button" class="ikon" data-hapus-rahasia="${esc(nama)}">Hapus</button>` : ""}</div>`;
  } else {
    el = `<input id="${id}" data-k="${esc(nama)}" type="text" value="${esc(nilai ?? "")}" ${opsi.daftar ? `list="${opsi.daftar}"` : ""} ${mati}>`;
  }
  return `<label for="${id}">${esc(a.label)}</label>${el}`;
}

function nilaiInput(el, a) {
  if (a.tipe === "boolean") return el.checked;
  if (a.tipe === "angka" || a.tipe === "bulat") return el.value === "" ? null : Number(el.value);
  if (a.tipe === "pilihan") {
    const p = a.pilihan.find((x) => String(x ?? "") === el.value);
    return p === undefined ? el.value : p;
  }
  if (a.tipe === "warna") return el.value.toUpperCase();
  return el.value.trim();
}

function pratinjauGaya(g) {
  const bayang = g.bayangan ? `${g.bayangan}px ${g.bayangan}px 0 rgba(0,0,0,.7)` : "none";
  const o = Math.max(0, g.outline);
  const garis = o ? [-o, 0, o].flatMap((x) => [-o, 0, o].map((y) => `${x}px ${y}px 0 ${g.warna_outline}`)).join(",") : "";
  const gaya = g.kotak
    ? `background:${g.warna_outline};padding:.1em .35em;text-shadow:${bayang};`
    : `text-shadow:${[garis, bayang !== "none" ? bayang : ""].filter(Boolean).join(",") || "none"};`;
  // ukuran ASS dirujuk ke tinggi 288; pratinjau 9:16 setinggi 320px
  return `<div class="pratinjau-gaya"><span style="font-family:'${esc(g.font)}',sans-serif;font-weight:${g.tebal ? 800 : 400};
    font-size:${(g.ukuran * 320 / 288).toFixed(1)}px;color:${g.warna};${gaya}bottom:${(g.posisi * 320 / 288).toFixed(0)}px">
    Contoh subtitle klip</span></div>`;
}

async function halamanPengaturan() {
  const [d, fonts] = await Promise.all([api("/api/settings"), api("/api/fonts").catch(() => [])]);
  const gayaKustom = JSON.parse(JSON.stringify(d.nilai.gaya_kustom || {}));
  const platform = JSON.parse(JSON.stringify(d.platform_efektif || {}));
  const semuaGaya = () => [...d.gaya_bawaan, ...Object.keys(gayaKustom)];
  const kelompok = {};
  for (const [k, a] of Object.entries(d.skema)) (kelompok[a.kelompok] ||= []).push(k);
  const pr = d.perangkat || { hardware: {}, rekomendasi: {}, otomatis: [] };
  const hw = pr.hardware;
  const NAMA_WHISPER = { cuda: hw.gpu_vendor === "amd" ? "GPU AMD (ROCm)" : "GPU (CUDA)", mlx: "GPU Apple (MLX)", cpu: "CPU" };
  const NAMA_ENCODER = { nvenc: "GPU NVIDIA (NVENC)", videotoolbox: "GPU Apple (VideoToolbox)", amf: "GPU AMD (AMF)", vaapi: "GPU (VAAPI)", cpu: "CPU (libx264)" };
  const pakaiGpu = pr.whisper !== "cpu" || pr.encoder !== "cpu";
  const kartuPerangkat = `<section class="kartu perangkat"><div class="baris renggang"><h2>Perangkat server</h2>
      <span class="lencana ${pakaiGpu ? "ok" : ""}">${pakaiGpu ? "GPU dipakai" : "CPU saja"}</span></div>
    <div class="spesifikasi">
      <div><small>CPU</small><strong>${esc(hw.cpu ?? "?")} core</strong></div>
      <div><small>RAM</small><strong>${hw.ram_gb != null ? `${esc(hw.ram_gb)} GB` : "tidak diketahui"}</strong></div>
      <div><small>GPU</small><strong>${hw.gpu ? `${esc(hw.gpu)}${hw.vram_gb ? ` · ${esc(hw.vram_gb)} GB` : ""}` : "tidak terdeteksi"}</strong></div>
      <div><small>Whisper</small><strong>${esc(NAMA_WHISPER[pr.whisper] || pr.whisper)}</strong></div>
      <div><small>Encoder video</small><strong>${esc(NAMA_ENCODER[pr.encoder] || pr.encoder)}</strong></div>
    </div>
    ${hw.gpu && !(hw.encoders || []).length ? `<p class="redup kecil">GPU terlihat, tapi tidak ada encoder GPU yang lolos uji encode di ffmpeg server ini (build ffmpeg/driver belum mendukung), jadi render memakai CPU.</p>` : ""}
    <p class="redup kecil">Dideteksi saat server mulai. Setelan bertanda <span class="lencana ok">sesuai perangkat</span> diisi otomatis dari spesifikasi ini${Object.keys(pr.rekomendasi).length ? ` (${Object.entries(pr.rekomendasi).map(([k, v]) => `${esc(d.skema[k]?.label || k)}: ${esc(v)}`).join(" · ")})` : ""}. Mengubahnya di bawah selalu menang.</p>
  </section>`;

  isi.innerHTML = `
  <div class="halaman-kepala"><div><span class="eyebrow">SESUAI CARA KERJAMU</span><h1>Pengaturan</h1>
    <p>Atur proses video, tampilan subtitle, dan format klip. Berlaku untuk proses berikutnya.</p></div>
    <button type="button" class="utama" id="simpan-set">${ikon("check")} Simpan perubahan</button></div>
  <datalist id="daftar-font">${fonts.map((f) => `<option value="${esc(f)}">`).join("")}</datalist>
  <div class="tumpuk" id="form-set">
    ${kartuPerangkat}
    ${Object.entries(kelompok).map(([nama, kunci]) => `
      <section class="kartu"><h2>${esc(nama)}</h2><div class="grid-form">
        ${kunci.map((k) => {
          const a = d.skema[k], env = d.terkunci_env[k], diubah = d.tersimpan.includes(k);
          const otomatis = pr.otomatis.includes(k), adaRek = k in pr.rekomendasi;
          return `<div class="medan">${inputDariSkema(k, a, d.nilai[k], { terkunci: !!env, gaya: semuaGaya() })}
            <div class="redup kecil">${env ? `<span class="lencana jalan">dikunci env ${esc(env)}</span> ` : ""}${otomatis && !env ? `<span class="lencana ok">sesuai perangkat</span> ` : ""}${diubah && !env && a.tipe !== "rahasia" ? `<a href="#" data-reset="${esc(k)}">${adaRek ? `kembalikan ke rekomendasi (${esc(pr.rekomendasi[k])})` : "kembalikan bawaan"}</a> · ` : ""}${esc(a.ket || "")}</div></div>`;
        }).join("")}
      </div></section>`).join("")}
    <section class="kartu"><div class="baris renggang"><h2>Gaya subtitle</h2>
      <div class="baris"><input id="nama-gaya" aria-label="Nama gaya subtitle baru" placeholder="nama-gaya-baru" pattern="[a-z0-9][a-z0-9-]{0,29}" style="width:12rem">
      <button type="button" id="tambah-gaya">+ Tambah gaya</button></div></div>
      <p class="redup kecil">Bawaan (tidak bisa diubah): ${d.gaya_bawaan.map(esc).join(", ")}. Pratinjau hanya perkiraan; hasil akhir dirender libass di server.</p>
      <div id="daftar-gaya"></div></section>
    <section class="kartu"><div class="baris renggang"><h2>Aturan platform</h2>
      <div class="baris"><input id="nama-platform" aria-label="Nama platform baru" placeholder="mis. facebook" style="width:10rem"><button type="button" id="tambah-platform">+ Platform</button></div></div>
      <p class="redup kecil">Durasi maks & catatan safe-zone yang tampil bersama caption per platform di Pustaka klip.</p>
      <div id="daftar-platform"></div></section>
  </div>`;

  // --- gaya
  function gambarGaya() {
    const el = $("#daftar-gaya");
    const nama = Object.keys(gayaKustom);
    el.innerHTML = nama.length ? nama.map((n) => `
      <div class="gaya-kustom" data-gaya="${esc(n)}">
        <div class="baris renggang"><strong>${esc(n)}</strong><button type="button" class="ikon" data-hapus-gaya="${esc(n)}">Hapus</button></div>
        <div class="gaya-isi"><div class="grid-form">${Object.entries(d.skema_gaya).map(([k, a]) =>
          `<div class="medan">${inputDariSkema(`${n}--${k}`, a, gayaKustom[n][k], { daftar: k === "font" ? "daftar-font" : null }).replace(/data-k="[^"]*"/, `data-gk="${esc(k)}"`)}</div>`).join("")}</div>
          ${pratinjauGaya(gayaKustom[n])}</div>
      </div>`).join("") : `<p class="kosong">Belum ada gaya kustom.</p>`;
  }
  $("#daftar-gaya").oninput = (e) => {
    const kartu = e.target.closest("[data-gaya]"), k = e.target.dataset.gk;
    if (!kartu || !k) return;
    const n = kartu.dataset.gaya;
    gayaKustom[n][k] = nilaiInput(e.target, d.skema_gaya[k]);
    kartu.querySelector(".pratinjau-gaya").outerHTML = pratinjauGaya(gayaKustom[n]);
  };
  $("#daftar-gaya").onclick = (e) => {
    const n = e.target.dataset.hapusGaya;
    if (n && confirm(`Hapus gaya ${n}?`)) { delete gayaKustom[n]; gambarGaya(); }
  };
  $("#tambah-gaya").onclick = () => {
    const n = $("#nama-gaya").value.trim();
    if (!/^[a-z0-9][a-z0-9-]{0,29}$/.test(n)) return toast("Nama gaya: huruf kecil, angka, tanda -", true);
    if (semuaGaya().includes(n)) return toast("Nama sudah dipakai", true);
    gayaKustom[n] = { ...d.gaya_baru };
    $("#nama-gaya").value = "";
    gambarGaya();
  };
  gambarGaya();

  // --- platform
  function gambarPlatform() {
    $("#daftar-platform").innerHTML = `<table><thead><tr><th>Platform</th><th>Durasi maks (dtk)</th><th>Catatan safe-zone</th></tr></thead><tbody>${
      Object.entries(platform).map(([p, v]) => `<tr data-p="${esc(p)}"><td>${esc(p)}</td>
        <td><input type="number" min="5" max="600" data-pf="maks_durasi" aria-label="Durasi maksimum ${esc(p)} dalam detik" value="${esc(v.maks_durasi)}" style="width:6rem"></td>
        <td><input type="text" maxlength="300" data-pf="catatan" aria-label="Catatan safe-zone ${esc(p)}" value="${esc(v.catatan)}" style="width:100%"></td></tr>`).join("")
    }</tbody></table>`;
  }
  $("#daftar-platform").oninput = (e) => {
    const tr = e.target.closest("tr"), f = e.target.dataset.pf;
    if (!tr || !f) return;
    platform[tr.dataset.p][f] = f === "maks_durasi" ? Number(e.target.value) : e.target.value;
  };
  $("#tambah-platform").onclick = () => {
    const p = $("#nama-platform").value.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9-]{0,29}$/.test(p)) return toast("Nama platform: huruf kecil, angka, tanda -", true);
    platform[p] ||= { maks_durasi: 60, catatan: "Jaga teks penting di area tengah layar 9:16." };
    $("#nama-platform").value = "";
    gambarPlatform();
  };
  gambarPlatform();

  // --- simpan
  async function kirim(perubahan, pesan = "Pengaturan disimpan") {
    try {
      await api("/api/settings", { method: "PUT", json: perubahan });
      INFO = await api("/api/info");
      toast(pesan);
      halamanPengaturan();
    } catch (err) { gagal(err); }
  }
  $("#form-set").onclick = (e) => {
    const k = e.target.dataset.reset;
    if (k) { e.preventDefault(); kirim({ [k]: null }, "Dikembalikan ke bawaan"); }
    const r = e.target.dataset.hapusRahasia;
    if (r && confirm("Hapus API key dari server?")) kirim({ [r]: null }, "API key dihapus");
  };
  $("#simpan-set").onclick = () => {
    const perubahan = {};
    for (const [k, a] of Object.entries(d.skema)) {
      const el = document.getElementById(`s-${k}`);
      if (!el || el.disabled) continue;
      const v = nilaiInput(el, a);
      if (a.tipe === "rahasia") { if (v) perubahan[k] = v; continue; }
      if (v === null) continue;
      if (JSON.stringify(v) !== JSON.stringify(d.nilai[k] ?? null)) perubahan[k] = v;
    }
    if (JSON.stringify(gayaKustom) !== JSON.stringify(d.nilai.gaya_kustom || {})) perubahan.gaya_kustom = gayaKustom;
    if (JSON.stringify(platform) !== JSON.stringify(d.platform_efektif || {})) perubahan.platform = platform;
    if (!Object.keys(perubahan).length) return toast("Tidak ada perubahan");
    kirim(perubahan);
  };
}

// ----------------------------------------------------------- tema & versi
const TEMA = ["otomatis", "terang", "gelap"];
function terapkanTema(t) {
  const el = document.documentElement;
  if (t === "terang") el.dataset.theme = "light";
  else if (t === "gelap") el.dataset.theme = "dark";
  else delete el.dataset.theme;
  const label = { otomatis: "Otomatis", terang: "Terang", gelap: "Gelap" }[t];
  $("#tombol-tema").innerHTML = `${ikon({ otomatis: "auto", terang: "sun", gelap: "moon" }[t])}<span>${label}</span>`;
  $("#tombol-tema").setAttribute("aria-label", `Tema ${label.toLowerCase()}. Klik untuk mengganti tema.`);
}
let temaKini = bacaLokal("tema", "otomatis");
if (!TEMA.includes(temaKini)) temaKini = "otomatis";
terapkanTema(temaKini);
$("#tombol-tema").onclick = () => {
  temaKini = TEMA[(TEMA.indexOf(temaKini) + 1) % TEMA.length];
  simpanLokal("tema", temaKini);
  terapkanTema(temaKini);
};
function tulisVersi() {
  const v = INFO.versi || {};
  $("#versi").innerHTML = v.commit
    ? `Clipper Studio <span aria-hidden="true">·</span> <code title="${esc(v.judul)} · ${esc(new Date(v.waktu).toLocaleString("id-ID"))}">${esc(v.commit)}</code>`
    : "Clipper Studio";
}

// ---------------------------------------------------------------- mulai
(async () => {
  try {
    [INFO, CAMPAIGNS] = await Promise.all([api("/api/info"), api("/api/campaigns")]);
    CAMPAIGNS = CAMPAIGNS.filter((c) => c.slug || c.error);
  } catch (e) { gagal(e); }
  tulisVersi();
  pantauJob();
  jalankanRute();
})();
