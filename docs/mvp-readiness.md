# Üretime hazırlık durumu — 8 Ekim 2026, arama hattı güncellemesi 24 Ekim 2026

Hedef: ekip kullanıcılarının ortak panelde araştırma oluşturması, gerçek kaynaklardan aday
bulması, kaynakları ve kanıtları kontrol edip onaylaması ve listeyi indirmesi; n8n'in aynı
API'yi güvenle çağırabilmesi.

## Doğrulama (24 Ekim 2026, arama hattı)

| Kontrol | Sonuç |
| --- | --- |
| Backend testleri, geçici SQLite | 341 geçti |
| Aynı testler, PostgreSQL 17 (geçici kapsayıcı) | 341 geçti |
| `ruff check` | temiz |
| Göç `20261024_search_provenance`: mevcut satırla yükseltme, geri alma, yeniden yükseltme, `alembic check` (PostgreSQL ve SQLite) | geçti; SQLite'ta CHECK kısıtları korunuyor |
| İzole Docker kurulumu (`-p rip-verify`, `APP_ENV=production`): `production_check.py --live --restart-worker` | 25/25 |
| `panel_smoke.py`, `e2e_collection.py` | geçti (4/4 senaryo) |
| Çıkarım, kör kontrol seti D1c (28 gerçek sayfa) | ilk ölçüm 392/601 kişi (%65,2), kesinlik %93,1; eski kod 2/601. Ayrıntı: `search-audit.md` |
| Canlı karşılaştırma, 6 talep | `search-audit.md`, "Uygulama durumu (24 Ekim 2026)" |

Gerçek kurulum 24 Ekim 2026'da kullanıcının isteğiyle güncellendi: doğrulanmış yedek
(`20261024T151419Z-0956a3ac.dump`), yeniden kurulum, göç `20261024_search_provenance`, 105 adayın
yeniden puanlanması. `.env` geliştirme ayarında kaldığı için (giriş kapalı) `production_check.py`
çalıştırılmadı; yalnızca okuma yapan kontroller (sağlık, panel, API) yapıldı. Geçiş komutları README
"5. Veritabanı" bölümünde.

## Doğrulama (8 Ekim 2026)

| Kontrol | Sonuç |
| --- | --- |
| Backend testleri, geçici SQLite | 198 geçti |
| Aynı testler, PostgreSQL 17 | 198 geçti |
| Aynı testler, production imajı içinde (`docker compose exec backend pytest`) | 198 geçti |
| `ruff check` | temiz |
| Migration: boş DB'ye kurulum, eski sürüm verisi üzerine yükseltme, `alembic check`, geri alma + yeniden yükseltme | geçti |
| Docker Compose (`APP_ENV=production`, giriş zorunlu): tüm servisler healthy | geçti |
| `scripts/production_check.py --live --restart-worker` | 25/25: Host koruması, yetkisiz erişim, giriş, güvenlik başlıkları, idempotent oluşturma/içe aktarma, n8n tekrar denemesi, servis anahtarının onaylayamaması, kalite bilgisi, CSV/XLSX/JSON/Sheets(mock), izleyici rolü, iptal, **gerçek web araması sırasında işçi yeniden başlatma → iş kaldığı yerden devam etti** |
| `scripts/e2e_collection.py` (Playwright) | 4/4 senaryo |
| `scripts/panel_smoke.py` (Playwright, giriş zorunlu) | geçti |
| `scripts/smoke.py` | geçti |
| Kontrollü kapanış | işçi SIGTERM ile 1,5 sn'de çıkış kodu 0; çalışan iş yeniden sıraya alındı |
| Güvensiz production ayarı (`AUTH_REQUIRED=false`) | başlatma reddedildi |

Doğrulanamayanlar: gerçek Google hesabıyla Sheets dışa aktarma (kimlik bilgisi yok; HTTP
sözleşmesi sahte sunucu ile test edildi), gerçek OpenAI çağrısı (isteğe bağlı), çalışan bir n8n
örneği (API sözleşmesi servis anahtarıyla test edildi; depoda n8n iş akışı yok).

## Gereksinim → çözüm

| Gereksinim | Çözüm | Sınır |
| --- | --- | --- |
| Kimlik doğrulama | Argon2 parola, sunucu tarafı oturum, hesap başına giriş sınırı, oturum rotasyonu | SSO/MFA/e-posta sıfırlama yok |
| Yetkilendirme | Yönetici / Araştırmacı / İzleyici; servis anahtarı onaylayamaz ve değerlendirilmiş kaydı değiştiremez | Ortak çalışma alanı; talep bazlı paylaşım yok |
| Arka plan işleri | PostgreSQL kuyruğu, ayrı işçi, kalp atışı, otomatik devam, iptal, kontrollü kapanış | Tek işçi önerilir |
| Idempotency | `Idempotency-Key` (oluşturma, içe aktarma, toplama, Sheets), kimlik eşleştirme, iş içinde URL tekilliği | Anahtarlar 7 gün saklanır |
| Toplama | robots.txt, yalnızca genel IP, DNS sabitleme, HTTPS→HTTP yönlendirme engeli, boyut/süre sınırı, yavaş sunucu koruması, sınırlı tekrar | HTML; PDF/JS sayfa yok |
| Çıkarım | Kurallı ve kanıta dayalı; CPU bütçesi | Her sayfa yapısını kapsamaz |
| Tekilleştirme | Kişisel e-posta/profil + uyumlu isim; ortak kutular ve şirket sayfaları kimlik sayılmaz; Türkçe karakter normalizasyonu | Belirsiz isimler ayrı kalır (insan inceler) |
| Veri kalitesi | İlgi/bilgi doluluğu puanı ve gerekçesi, kaynak sayısı, alan adları, ilk/son görülme, kaynak kanıtı, doğrulama durumu | Puan bir öneridir |
| Dışa aktarma | Deterministik CSV/XLSX/JSON, formül enjeksiyonu ve geçersiz karakter koruması; Google Sheets (RAW, tekrar güvenli) | Sheets gerçek hesapla test edilmedi |
| Gözlemlenebilirlik | JSON log, istek/iş kimliği, aşama sayaçları, denetim kaydı | Merkezi log/izleme sistemi yok |
| Hata yönetimi | Tek hata biçimi (`code`, `retryable`, `request_id`), Türkçe panel mesajları, HTML hata sayfası | — |
| Güvenlik başlıkları | CSP, frame-ancestors, nosniff, no-referrer, no-store; Host doğrulama; gövde boyutu sınırı | HTTPS ters vekil kurulumu kullanıcıya ait |
| Veri saklama | Sayfa metni 90 gün sonra silinir; süresi dolmuş oturumlar temizlenir | Aday verisi için saklama süresi kurum kararı |

## Canlıya almadan önce yapılacaklar (kod dışı)

1. `.env`: `APP_ENV=production`, `AUTH_REQUIRED=true`, `ENABLE_DEMO_DATA=false`, `DEMO_MODE=false`,
   `ALLOWED_ORIGINS=` (boş) ve sunucu adını içeren `ALLOWED_HOSTS`.
2. Ağa açılacaksa HTTPS ters vekil + `COOKIE_SECURE=true` + güvenlik duvarı.
3. Günlük yedek zamanlaması (`scripts/backup.py --verify`) ve cihaz dışı kopya.
4. Kişisel veri işleme (KVKK) değerlendirmesi ve aday verisi saklama süresi kararı.
5. Google Sheets kullanılacaksa bir deneme dışa aktarması.

## Yönetici parola kurtarma

```sh
docker compose exec backend python -m app.manage reset-password admin@example.com
```

Yeni parola gizli girişle iki kez sorulur; komut geçmişine veya loglara yazılmaz. Tüm eski
oturumlar iptal edilir. `.env` başlangıç parolasını değiştirmek mevcut kullanıcıyı değiştirmez.

## Araştırılan kaynaklar

- [DDGS sağlayıcısı](https://github.com/deedy5/ddgs): arama adaptörü; 9.16.0 sürümü sabitlenmiştir.
- [FastAPI şablonları](https://fastapi.tiangolo.com/advanced/templates/): Python paneli.
- [Docker Compose işletimi](https://docs.docker.com/compose/how-tos/production/): tek sunucuda servis düzeni.
- [Önceki scraper değerlendirmesi](scraper-architecture.md): upstream kodu kopyalanmadı.
