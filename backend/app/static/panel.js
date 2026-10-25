"use strict";
const feedback = document.getElementById("feedback");
const STATUS_MESSAGES = {
  401: "Oturumunuz sona erdi. Lütfen yeniden giriş yapın.",
  403: "Bu işlem için yetkiniz yok.",
  404: "Kayıt bulunamadı. Silinmiş olabilir; sayfayı yenileyin.",
  409: "Bu kayıt şu anda başka bir işlem tarafından kullanılıyor. Biraz sonra yeniden deneyin.",
  413: "Gönderilen veri çok büyük.",
  429: "Çok fazla istek gönderildi. Bir dakika sonra yeniden deneyin.",
  500: "Beklenmeyen bir hata oluştu. Sorun sürerse yöneticinize hata kodunu iletin.",
  502: "Dış servise ulaşılamadı. Biraz sonra yeniden deneyin.",
  503: "Servis geçici olarak kullanılamıyor. Biraz sonra yeniden deneyin.",
};
function report(message, error=false) { feedback.textContent=message; feedback.hidden=false; feedback.className=error?"error":""; feedback.scrollIntoView({behavior:"smooth",block:"nearest"}); }
function newKey() { return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); }
function describe(status, value) {
  if (status === 422 && Array.isArray(value.detail)) return value.detail.map(e => e.loc.slice(1).join(".") + ": " + e.msg).join("\n");
  // 409/422 details explain the conflict (for example "already running"); others use Turkish text.
  const detail = typeof value.detail === "string" && [400, 409, 422].includes(status) ? value.detail : "";
  const base = STATUS_MESSAGES[status] || detail || "İşlem başarısız.";
  const text = detail && detail !== base ? base + " (" + detail + ")" : base;
  return value.request_id && status >= 500 ? text + " Hata kodu: " + value.request_id : text;
}
async function send(path, method="POST", data, key) {
  const headers = {"Content-Type":"application/json","X-Requested-With":"RelationshipPlatform"};
  if (key) headers["Idempotency-Key"] = key;
  let response;
  try {
    response = await fetch(path, {method, credentials:"same-origin", headers, body: data === undefined ? undefined : JSON.stringify(data)});
  } catch (_) {
    throw new Error("Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.");
  }
  if (!response.ok) {
    let value;
    try { value = await response.json(); } catch { value = {}; }
    if (response.status === 401 && !path.startsWith("/api/v1/auth/")) location.assign("/panel/login");
    throw new Error(describe(response.status, value));
  }
  return response;
}
document.querySelectorAll("form[data-api]").forEach(form => {
  // One key per page load: a retried submit after a lost response cannot create a duplicate.
  const key = newKey();
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const data = {};
      for (const element of form.elements) {
        if (!element.name) continue;
        let value = element.value;
        if (element.dataset.list) value = value.split(",").map(s => s.trim()).filter(Boolean);
        else if (element.type === "number") value = Number(value);
        else if (element.dataset.nullable === "true" && !value) value = null;
        data[element.name] = value;
      }
      const method = form.dataset.method || "POST";
      const response = await send(form.dataset.api, method, data, method === "POST" ? key : undefined);
      const result = await response.json();
      if (form.dataset.researchRedirect) location.assign("/panel/research/" + encodeURIComponent(result.id));
      else if (form.dataset.redirect) location.assign(form.dataset.redirect);
      else location.reload();
    } catch (error) { report(error.message, true); button.disabled = false; }
  });
});
document.querySelectorAll("button[data-action]").forEach(button => {
  const key = newKey();
  button.addEventListener("click", async () => {
    if (button.dataset.confirm && !window.confirm(button.dataset.confirm)) return;
    button.disabled = true;
    const original = button.textContent;
    if (button.dataset.action.endsWith("/collect")) button.textContent = "Arama başlatılıyor…";
    try {
      await send(button.dataset.action, "POST", undefined, key);
      if (button.dataset.redirect) location.assign(button.dataset.redirect); else location.reload();
    } catch (error) { report(error.message, true); button.disabled = false; button.textContent = original; }
  });
});
document.querySelectorAll("button[data-export]").forEach(button => button.addEventListener("click", async () => {
  button.disabled = true;
  try {
    const format = document.getElementById("export-format").value;
    const includeAll = Boolean(document.getElementById("export-all")?.checked);
    const response = await send("/api/v1/research-requests/" + button.dataset.export + "/exports", "POST", {format, include_all: includeAll}, newKey());
    if (format === "sheets") {
      const result = await response.json();
      if (result.url) { window.open(result.url, "_blank", "noopener"); report(result.row_count + " aday Google Sheets'e aktarıldı."); }
      else report(result.message || "Google Sheets bağlı değil; önizleme oluşturuldu.");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = (includeAll ? "tum-adaylar." : "onayli-adaylar.") + format; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    report(includeAll ? "Tüm adaylar indirildi." : "Onaylı adaylar indirildi.");
  } catch (error) { report(error.message, true); } finally { button.disabled = false; }
}));
