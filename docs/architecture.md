# Mimari

Tek sunucu, küçük ekip (10–20 kullanıcı) için tasarlandı. Bileşenler:

```text
Tarayıcı (Jinja2 panel)      n8n / otomasyon (Bearer anahtar)
          \                      /
           FastAPI (tek süreç)  ── /api/v1, /panel, /health
             │  Host kontrolü, istek boyutu sınırı, hız sınırı,
             │  istek kimliği, güvenlik başlıkları, tek hata biçimi
             ▼
        PostgreSQL ── araştırmalar, adaylar, kaynaklar, iş kuyruğu,
             ▲         idempotency kayıtları, denetim kaydı
             │
        Python işçisi (tek süreç) ── kuyruktan iş alır, dış web'e çıkar
```

API ve panel aynı süreçtir; uzun süren her iş (web araması) işçide çalışır.
HTTP isteği hiçbir zaman aramanın bitmesini beklemez.

## Araştırma hattı

`services/collection.py` içindeki `CollectionRun` her işi aşağıdaki aşamalarla yürütür.
Her aşama ayrı bir modüldür ve test edilirken sahte (fake) sağlayıcı verilebilir.

| Aşama | Modül | Sorumluluk |
| --- | --- | --- |
| Talep doğrulama | `schemas.py` | Pydantic; alan uzunlukları, dil, adet, URL şeması |
| Gereksinim modeli | `requirements.py`, `topics.py` | Talepten yapılandırılmış şartname: istenen roller (VEYA), konu terimleri ve eşanlamlıları (6 dilde), şehir/ülke, sorgu dili ve ikinci dil (`build_spec`) |
| Sorgu planı | `requirements.py` | Amaçlı sorgu turları (`plan`, `query_rounds`): kadro/ekip/konuşmacı/jüri listeleri, anahtar kelime, profil platformları, terim çevirileri ve eşanlamlılar, etkinlik konuşmacıları, şehirsiz geniş tur |
| Keşif | `discovery.py` | Değiştirilebilir `DiscoveryProvider`; varsayılan anahtarsız DDGS; tüm motorlar boşsa bekleyip bir kez daha sorar; motor ve sıra bilgisi kaynağa yazılır |
| Ön eleme ve öncelik | `triage.py` | Sayfa türü (kişi listesi, profil, etkinlik, haber, ilan, tanım, belge, ürün, kapalı platform) ve öncelik; ilan/tanım/PDF açılmadan "Ön eleme" notuyla atlanır; ilgili sayfadan aynı sitenin ekip/kadro sayfasına bağlantı (`follow_links`) |
| Toplama | `fetching.py` | robots.txt, yalnızca genel IP, DNS sabitleme, yönlendirme kontrolü, boyut/süre sınırı, gözetimli zaman aşımı, yeniden deneme |
| Çıkarım | `extraction.py`, `record_blocks.py`, `mentions.py`, `page_context.py` | Siteden bağımsız kişi listesi çıkarımı (tekrar eden kayıt blokları, unvanlar, "Rol: Ad", "Soyad, Ad"); her kişinin rolü, uzmanlığı, profil bağlantısı ve herkese açık e-postası yalnızca kendi bloğundan; haber metinlerinde unvan/rol ile anılan kişiler; sayfa sahibinin kurumu ve adresi (çıkarıldı olarak işaretli); JSON-LD, profil başlığı, etiketli biyografi; CPU bütçesi |
| Eşleştirme | `matching.py` | Rol / konu / konum / anahtar kelime için ayrı karar (uyuyor, çıkarıldı, bilinmiyor, uymuyor) ve dayanağı; rolü uymayanlar alınmaz; başka konumdakiler alınır ama hedefe sayılmaz |
| Platform ipuçları | `platforms.py` | LinkedIn, ResearchGate, Crunchbase, F6S, The Official Board sonuçları açılmaz; arama sonucu başlığından doğrulanmamış ipucu |
| Normalizasyon + tekilleştirme | `candidates.py`, `deduplication.py` | Talep kapsamında, ihtiyatlı kimlik eşleştirme; insan kararlarını koruma |
| Puanlama | `scoring.py` | İlgi puanı eşleştirme kararlarının puanlarının toplamı (+ kanıt puanı); kararlar `candidates.match_details` içinde; bilgi doluluğu puanı |
| İnsan değerlendirmesi | panel, `PATCH /candidates/{id}` | Yalnızca insan onaylar; servis anahtarı onaylayamaz |
| Dışa aktarma | `export.py` | CSV/XLSX/JSON; isteğe bağlı Google Sheets |
| Denetim | `AuditLog`, JSON loglar | Kim, ne, ne zaman; istek kimliği ile |

Bir kaynağın başarısız olması işi düşürmez. Her kaynağın sonucu (`EXTRACTED`,
`NEEDS_REVIEW`, `FAILED`, `SKIPPED`, `DUPLICATE`, `NOT_NEEDED`) ve hata nedeni saklanır. Kaynakta
ayrıca hangi sorgudan (`query`), hangi motordan (`engine`) ve kaçıncı sırada (`rank`) geldiği, sayfa
türü (`page_kind`) ve öncelik (`priority`) tutulur; böylece sorgu başına verim ölçülebilir.
İş sayaçları `collection_jobs.stats` içindedir: sorgu turu, sorgu, arama sonucu, boş sorgu
(`search_empty`), tekrar eden adres, ön elemede atlanan (`triage_skipped`), izlenen bağlantı
(`links_followed`), aynı içerik, çıkarılan/nitelenen kişi, başka konumdaki kişi
(`profiles_elsewhere`), oluşturulan/birleştirilen aday, platform ipucu (`platform_leads`).

**Okuma sırası:** kaynaklar arama sırasıyla değil, ön elemenin önceliğine göre okunur (kişi
listesi > profil > etkinlik > genel sayfa > haber; konu, şehir ve rol kelimesi eşleşmesi öncelik
ekler). İzlenen ekip/kadro bağlantıları sıradaki arama sonuçlarından önce okunur. Kişi çıkmayan ama
konuyla ilgili bir sayfadan aynı alan adındaki en fazla 3 kişi listesi bağlantısı izlenir; iş başına
`COLLECTION_MAX_FOLLOWED_LINKS` (30).

**Hedef sayımı:** hedefe yalnızca sayfa kanıtı olan, rolü uyan (veya sayfadan çıkarılan) ve konumu
çelişmeyen kişiler sayılır. Bir sayfadaki kişiler içe aktarılmadan önce talebe uygunluğa göre
sıralanır. Kendi kaydına veya sayfa adresine göre başka bir şehirde olanlar ("Konum farklı")
değerlendirme için listelenir, istenen adet kadarla sınırlıdır ve aramayı bitirmez.

**Platform ipuçları:** otomatik okumayı yasaklayan profil platformlarının sayfaları hiç getirilmez.
Arama sonucunun başlığı ad, rol ve kurum veriyorsa kişi "platform ipucu" olarak eklenir: kaynak türü
`platform_search_result`, güven puanı en fazla 15, gerekçede "doğrulanmadı". İpuçları istenen adet kadarla
sınırlıdır ve hedefi doldurmaz; arama sayfa kanıtlı kişiler için sürer.

**Sorgu turları:** keşif tek seferlik değildir. Sırasıyla (1) ana konu + şehir + kişi listesi
sayfası ("akademik kadro", "kurucu ekibimiz", "konuşmacılar") ve ilk anahtar kelime + rol, (2) profil
platformları (`linkedin …`, akademik taleplerde `researchgate …`), (3) konunun ikinci dildeki adı ve
eşanlamlıları ("artificial intelligence Istanbul faculty members", "görüntü işleme"), (4) alanın diğer
parçaları ve anahtar kelimeler (Türkçe akademik taleplerde `site:edu.tr`), (5) etkinlik konuşmacıları,
(6) şehirsiz geniş sorgular denenir; bir sorgu sonraki turlarda tekrarlanmaz. "Otomatik" dilde Türkiye'deki
bir şehir Türkçe sorgu ve `tr-tr` bölgesiyle aranır. Arapça taleplerde alan ve şehir de Arapçaya çevrilir.
"kimdir", "biyografi" gibi ekler kullanılmaz: tanım yazıları ve ünlü kişi sayfaları getiriyordu.

**Sonuç sayfaları:** turlar 1. sonuç sayfasında bitince aynı turlar 2., 3., … sayfa için
tekrarlanır (en fazla `RESULT_PAGES` = 5). Bir sorgunun sonraki sayfası yalnızca son sayfası yeni
kaynak getirdiyse istenir. Yeni adres getirmeyen sorgular `stats.spent_queries` içinde saklanır.
1. sayfadan sonraki her sorgudan önce `SEARCH_PAUSE_SECONDS` (2 sn), 1. sayfa sorguları arasında
`SEARCH_QUERY_INTERVAL_SECONDS` (1 sn) beklenir: art arda gönderilen sorgular ücretsiz motorlarda çok
daha sık boş dönüyordu.

**Durma:** iş şu durumlardan ilki gerçekleşince durur:
- istenen adet doldu,
- kullanıcı "Aramayı durdur" dedi,
- aranacak yeni kaynak kalmadı,
- `COLLECTION_MAX_SOURCES` (500) doldu,
- `COLLECTION_TIME_BUDGET_SECONDS` (60 dk) güvenlik tavanına ulaşıldı.

Yeni kişi bulunamayan süre işi durdurmaz. Tavan, tek işçinin başka talepleri sonsuza kadar
bekletmemesi içindir. Bitiş mesajı nedeni ve denenen sorgu/kaynak/sayfa sayısını söyler.
Tamamlanan adım `stats.stage` (`round:N`, sayfalar boyunca sayılır) içinde saklanır;
yeniden başlayan iş kaldığı adımdan devam eder. Arama motorunun "sonuç yok" yanıtı hata
sayılmaz ve tekrar denenmez.

## Durum makineleri

Toplama işi (`collection_jobs.status`):

```text
QUEUED ──işçi alır──▶ RUNNING ──▶ COMPLETED | PARTIAL | NO_RESULTS | FAILED | CANCELLED
  │                    │  ▲
  │ iptal              │  └── kalp atışı durursa veya SIGTERM: yeniden QUEUED (deneme < COLLECTION_MAX_ATTEMPTS)
  ▼                    └── iptal isteği: o anki kaynak bitince CANCELLED
CANCELLED
```

Araştırma talebi (`research_requests.status`): `CREATED` → (iş sırasında) `SEARCHING`/`COLLECTING`
→ `READY_FOR_REVIEW` (aday varsa) | `NO_RESULTS` | `FAILED` → insan `COMPLETED` yapabilir.
Mevcut aday varsa iş başarısız olsa bile talep incelenebilir kalır.

## Güvenilirlik

- **Kalp atışı:** işçi her adımda `heartbeat_at` yazar. `COLLECTION_STALE_AFTER_SECONDS` boyunca
  güncellenmeyen iş, işçi çökmüş kabul edilip yeniden sıraya alınır; deneme hakkı bitince `FAILED`.
- **Kontrollü kapanış:** `docker stop` → SIGTERM → işçi o anki adımı bitirir, işi `QUEUED` yapar,
  yeniden başlayınca kaldığı kaynaktan devam eder (bulunan kaynaklar tekrar eklenmez).
- **Yeniden deneme:** arama sağlayıcısı ve geçici HTTP hataları (zaman aşımı, 429, 5xx) üstel
  geri çekilmeyle sınırlı sayıda tekrarlanır; iş bütçesi (`COLLECTION_TIME_BUDGET_SECONDS`) aşılmaz.
  Kalıcı hatalar (robots yasağı, 404, HTML olmayan içerik, SSRF engeli) tekrarlanmaz.
- **Yavaş sunucular:** belge başına mutlak süre sınırı soket kapatılarak uygulanır; damla damla
  veri gönderen sunucu işçiyi kilitleyemez.

## Idempotency (tekrar güvenliği)

| İşlem | Strateji |
| --- | --- |
| Araştırma oluşturma, aday ekleme, toplu aday, toplama başlatma | `Idempotency-Key` başlığı: sonuç işle aynı transaction'da saklanır; tekrar istek ilk yanıtı döndürür. Yarışan iki istekte benzersiz kısıt ikincisini geri alır. |
| Aday içe aktarma (anahtarsız da) | Kimlik eşleştirme: aynı kişi + aynı kaynak birleştirilir, kaynak URL'si aday başına benzersiz |
| Toplama işi tekrarı (çökme/yeniden başlatma) | Aynı iş devam eder; kaynak URL'si iş içinde benzersiz; içe aktarma birleştirir |
| Google Sheets dışa aktarma | `Idempotency-Key` ile aynı tablo yeniden kullanılır; yazma "temizle + aynı aralığa yaz" olduğundan satır çoğalmaz |
| Durum değişikliği, PATCH | Doğası gereği idempotent |

## Tekilleştirme kuralları

Yalnızca aynı araştırma talebi içinde eşleşir. İsimler her durumda uyumlu olmalıdır.

1. Kişisel e-posta (info@, iletisim@ gibi ortak kutular hariç) **veya** kişisel profil URL'si
   (`linkedin.com/in/...`; şirket sayfaları hariç; `tr.linkedin.com` = `linkedin.com`) + uyumlu isim
   (göbek adı farkı kabul edilir).
2. Aynı normalize isim (Türkçe ı/İ dahil) + aynı kaynak URL'si.
3. Aynı/çok benzer isim (≥0.94) + aynı kurum veya aynı alan adı.
4. Farklı kişisel e-posta veya farklı LinkedIn profili her zaman iki ayrı kişidir.

İnsan tarafından değerlendirilmiş (APPROVED/REJECTED/CONTACTED/ARCHIVED) kayıtların alanları
otomatik olarak değiştirilmez; yalnızca yeni kaynak/kanıt eklenir.

## Yetkilendirme

| Rol | Yetki |
| --- | --- |
| ADMIN | Her şey + kullanıcı/rol yönetimi, silme, denetim kaydı |
| USER (Araştırmacı) | Araştırma oluşturma/düzenleme, toplama başlatma/iptal, aday değerlendirme, dışa aktarma |
| VIEWER (İzleyici) | Okuma ve dışa aktarma |
| SERVICE (n8n anahtarı) | Araştırma oluşturma, toplama tetikleme, aday içe aktarma, not ekleme; **onay ve değerlendirilmiş kaydı değiştirme yok** |
| LOCAL (`AUTH_REQUIRED=false`) | Yalnızca geliştirme; production'da başlatma reddedilir |

Çalışma alanı ekip içinde ortaktır: tüm giriş yapmış kullanıcılar tüm araştırmaları görür.
Rol değişikliği ve pasifleştirme mevcut oturumları anında kapatır.

## Gözlemlenebilirlik

Tüm loglar tek satır JSON'dur (`ts`, `level`, `logger`, `event`, `request_id`, alanlar).
İstemci `X-Request-ID` gönderirse (ör. n8n yürütme kimliği) aynı kimlik loglara, denetim
kaydına ve yanıta taşınır. Örnek olaylar: `collection.started`, `discovery.results`,
`discovery.failed`, `source.processed`, `source.failed`, `collection.requeued_on_shutdown`,
`collection.finished` (tüm sayaçlarla), `export.completed`, `http.request`, `http.unhandled_error`
(yalnızca sunucu logunda tam hata izi). Parola, anahtar, çerez ve sayfa metni loglanmaz.

## Hata biçimi

Her API hatası: `{"detail", "code", "retryable", "request_id"}`. Kodlar: `validation_error`,
`authentication_required`, `permission_denied`, `not_found`, `conflict`, `payload_too_large`,
`rate_limited`, `external_service_error`, `internal_error`. `retryable=true` (409, 429, 502–504)
aynı isteğin daha sonra tekrarlanabileceğini belirtir. Panel bu kodları Türkçe mesajlara çevirir.

## Yapay zekâ katmanı

Hat LLM kullanmaz. `services/ai.py` isteğe bağlı `/ai/*` uçları içindir: şema doğrulama
(Pydantic), zaman aşımı, sınırlı yeniden deneme, çıktı token sınırı, `PROMPT_VERSION`,
girdi kısaltma. Sağlayıcı hatası iş akışını durdurmaz; deterministik puanlama her zaman çalışır.
