"use strict";
(() => {
  const root = document.querySelector("[data-collection]");
  if (!root) return;
  const element = name => root.querySelector(`[data-${name}]`);
  const labels = {DISCOVERED:"Sırada", READING:"Okunuyor", EXTRACTED:"Aday bulundu", NEEDS_REVIEW:"İncelendi", FAILED:"Erişilemedi", SKIPPED:"Atlandı", NOT_NEEDED:"Hedefe ulaşıldı", DUPLICATE:"Aynı içerik"};
  let elapsed = 0, synced = Date.now(), stopped = false, timer;
  const tick = setInterval(() => {
    const seconds = elapsed + Math.floor((Date.now() - synced) / 1000);
    element("elapsed").textContent = seconds < 60 ? `${seconds} sn` : `${Math.floor(seconds / 60)} dk ${seconds % 60} sn`;
  }, 1000);
  function link(text, href) {
    const a = document.createElement("a");
    const url = new URL(href, location.origin);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("Invalid source URL");
    a.textContent = text; a.href = url.href;
    return a;
  }
  function render(data) {
    const {job, progress, candidates, sources} = data;
    elapsed = progress.elapsed_seconds; synced = Date.now();
    element("source-count").textContent = job.discovered;
    element("processed-count").textContent = job.processed;
    element("candidate-count").textContent = data.total_candidates;
    for (const [key, value] of Object.entries({total:data.total_candidates, approved:data.approved, awaiting:data.awaiting_review})) {
      const metric = document.querySelector(`[data-metric="${key}"]`);
      if (metric) metric.textContent = value;
    }
    const phase = {queued:"Arama sırada", searching:"Kaynaklar aranıyor", fallback:"Arama genişletiliyor", reading:"Kaynaklardan kişiler çıkarılıyor", cancelling:"Arama durduruluyor"};
    let round = progress.round > 1 || progress.page > 1 ? ` · tur ${progress.round}/${progress.rounds}` : "";
    if (progress.page > 1) round += ` · ${progress.page}. sonuç sayfası`;
    element("phase").textContent = (phase[progress.phase] || "Sonuçlar hazırlanıyor") + round;
    let detail = "İlk sonuçları almak için arama motorları taranıyor.";
    if (progress.phase === "queued") detail = "Önceki arama tamamlanınca bu işlem otomatik başlayacak.";
    if (progress.phase === "cancelling") detail = "Şu anki kaynak bitince arama duracak. Bulunan adaylar korunur.";
    if (progress.phase === "fallback") detail = "Hedef sayıya henüz ulaşılmadı. Arama farklı sorgularla ve sonraki sonuç sayfalarıyla sürüyor; hedefe ulaşınca, siz durdurunca, yeni kaynak kalmayınca veya güvenlik süre sınırı dolunca biter.";
    if (progress.phase === "reading") detail = progress.current_source ? `Şu an okunuyor: ${new URL(progress.current_source).hostname}` : "Bulunan kaynaklar inceleniyor.";
    element("search-detail").textContent = detail;
    const bar = root.querySelector("progress");
    if (progress.phase === "reading" && job.discovered) bar.value = Math.round(job.processed / job.discovered * 100);
    else bar.removeAttribute("value");
    element("connection").textContent = progress.blocked ? `Canlı güncelleniyor · ${progress.blocked} kaynak okunamadı, diğerleriyle devam ediliyor.` : "Canlı güncelleniyor";
    const sourceList = element("live-sources");
    sourceList.replaceChildren();
    const visible = sources.filter(s => s.status !== "DISCOVERED").slice(-6);
    for (const source of (visible.length ? visible : sources.slice(0, 6))) {
      const li = document.createElement("li");
      const a = link(source.title || new URL(source.url).hostname, source.url);
      a.target = "_blank"; a.rel = "noopener noreferrer";
      const badge = document.createElement("small"); badge.textContent = labels[source.status] || source.status;
      li.append(a, badge); sourceList.append(li);
    }
    if (!sourceList.children.length) { const li = document.createElement("li"); li.textContent = "Arama motorlarından yanıt bekleniyor…"; sourceList.append(li); }
    const people = element("live-candidates"); people.replaceChildren();
    for (const candidate of candidates.slice(0, 8)) {
      const li = document.createElement("li");
      li.append(link(candidate.full_name, `/panel/candidates/${encodeURIComponent(candidate.id)}`));
      const note = document.createElement("small"); note.textContent = candidate.job_title || "Kaynaklı aday · inceleme bekliyor";
      li.append(note); people.append(li);
    }
    if (!people.children.length) { const li = document.createElement("li"); li.textContent = "İlk profil henüz bulunmadı. Arama devam ediyor."; people.append(li); }
  }
  async function poll() {
    let delay = 1500;
    try {
      const response = await fetch(root.dataset.collection, {credentials:"same-origin", signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error("Progress unavailable");
      const data = await response.json();
      if (data.job && !["QUEUED", "RUNNING"].includes(data.job.status)) { stopped = true; clearInterval(tick); location.reload(); return; }
      if (!data.job) { stopped = true; clearInterval(tick); element("connection").textContent = "Bu araştırma için çalışan bir arama bulunamadı. Sayfayı yenileyin."; return; }
      render(data);
    } catch (_) {
      element("connection").textContent = "Bağlantı yenileniyor… Arama arka planda devam ediyor; yeniden kontrol edilecek.";
      delay = 4000;
    }
    if (!stopped) timer = setTimeout(poll, delay);
  }
  window.addEventListener("pagehide", () => {stopped = true; clearTimeout(timer); clearInterval(tick);});
  poll();
})();
