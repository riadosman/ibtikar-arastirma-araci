# İBTİKAR Araştırma Aracı

İBTİKAR ilişkiler ofisi için kişi araştırma ve aday değerlendirme platformu.

Ekip bir araştırma talebi girer: alan, konum, hedef profil ve aday sayısı. Sistem herkese açık
web'de arar, bulunan sayfaları okur, kişileri kaynak kanıtıyla birlikte çıkarır, tekilleştirir ve
puanlar. Adaylar ekip tarafından incelenir; onaylanan liste CSV, Excel, JSON veya Google Sheets
olarak dışa aktarılır.

> **Son karar her zaman insandadır.** Otomatik aramadan veya n8n'den gelen hiçbir aday onaylı
> başlamaz.

**Teknoloji:** Python 3.11 · FastAPI · SQLAlchemy 2 + Alembic · PostgreSQL 17 · Jinja2 · Docker Compose

## İçindekiler

- [Özellikler](#özellikler)
- [Hızlı başlangıç](#hızlı-başlangıç)
- [Kullanım](#kullanım)
- [Mimari](#mimari)
- [Veri modeli](#veri-modeli)
- [Yapılandırma](#yapılandırma)
- [Çalıştırma ve bakım](#çalıştırma-ve-bakım)
- [Production dağıtımı](#production-dağıtımı)
- [Entegrasyonlar](#entegrasyonlar)
- [Geliştirme ve test](#geliştirme-ve-test)
- [Arama kalitesi](#arama-kalitesi)
- [Proje yapısı](#proje-yapısı)
- [Sorun giderme](#sorun-giderme)
- [Bilinen sınırlamalar](#bilinen-sınırlamalar)
- [Belgeler](#belgeler)

## Özellikler

- **Amaca yönelik arama:** Talepten rol, konu (eşanlamlılarıyla) ve konum gereksinimleri
  çıkarılır. Sorgular kişilerin listelendiği kadro, ekip ve konuşmacı sayfalarını hedefler.
- **Ücretsiz, anahtarsız arama:** DDGS üzerinden Yahoo, DuckDuckGo, Brave, Google, Mojeek ve
  Startpage kullanılır. Ücretli bir arama API'si gerekmez.
- **Kanıtlı adaylar:** Her adayın kaynak sayfası ve o sayfadan kısa bir alıntı saklanır.
- **Çok dilli:** Türkçe, İngilizce, Almanca, Fransızca, İspanyolca ve Arapça kaynaklar. Arapça
  adlar için ayrı kurallar vardır.
- **Tekilleştirme:** Aynı kişi farklı sayfalarda bulunsa da tek kayıt olur; yeni kaynaklar mevcut
  kayda eklenir.
- **Açıklanabilir puan:** Rol, konu ve konum kararları gerekçeleriyle aday kaydında tutulur.
- **İnsan onaylı iş akışı:** Durum takibi, notlar, elle aday ekleme ve rol bazlı yetki.
- **Dayanıklı arka plan işçisi:** İş kuyruğu PostgreSQL'dedir. Yeniden başlatmada iş kaldığı
  yerden sürer; arama istendiği an durdurulabilir.
- **Entegrasyonlar:** n8n için Bearer anahtarlı ve idempotency destekli REST API, Google Sheets
  dışa aktarma.
- **Güvenlik:** Argon2 parola özeti, CSP, Host başlığı denetimi, hız sınırı, SSRF korumalı ve
  robots.txt kurallarına uyan sayfa okuma, denetim kaydı.

## Hızlı başlangıç

### Gereksinimler

- Docker Desktop (Linux container) ve Docker Compose v2
- Python 3.11+ (yalnızca kurulum yardımcısı, yedekleme ve yerel testler için)
- İşçi servisinin dış web'e HTTPS erişimi

### Kurulum

```powershell
python scripts/init_env.py      # .env oluşturur; parola ve anahtarları rastgele üretir
docker compose build backend    # backend ve worker'ın ortak imajını oluşturur
docker compose up -d --wait     # db, backend ve worker servislerini başlatır
docker compose ps               # üç servis de "healthy" olmalı
```

| Adres | Açıklama |
| --- | --- |
| http://localhost:3100 | Panel. Giriş bilgileri `.env` içindeki `ADMIN_EMAIL` / `ADMIN_PASSWORD` |
| http://localhost:8100/api/v1 | REST API |
| http://localhost:8100/docs | API belgeleri (`ENABLE_API_DOCS=false` ile kapatılır) |
| http://localhost:8100/health | Sağlık kontrolü |

- `.env` hiçbir zaman Git'e eklenmez. `init_env.py` var olan bir `.env` dosyasının üzerine yazmaz.
- Yeni kullanıcılar panelde **Kullanıcılar** ekranından eklenir.

## Kullanım

### Araştırma akışı

1. **Yeni araştırma** formunu doldurun ve **Kaydet**'e basın.
2. Açılan araştırma sayfasında **Web'de ara**'ya basın. İş sıraya alınır ve ilerleme sayfada canlı
   görünür. **Aramayı durdur** ile istediğiniz an durdurabilirsiniz; bulunan adaylar korunur.
3. Adayları inceleyin: kaynak bağlantısını açın, durumu güncelleyin, not ekleyin. Aramanın
   bulamadığı biri varsa **Kaynaklı aday ekle** ile elle ekleyin.
4. Toplama bittiğinde **Toplama tamamlandı / değerlendirmeye geç**'e basın.
5. **İndir** ile CSV, Excel, JSON veya Google Sheets olarak dışa aktarın. Varsayılan olarak
   yalnızca onaylı adaylar aktarılır; **Tüm adaylar** seçeneği hepsini içerir.

### Form alanları

| Alan | Açıklama | Örnek |
| --- | --- | --- |
| Başlık | Talebin kısa adı | Yapay Zekâ Paneli – Akademisyenler |
| Amaç ve açıklama | Talebin amacı ve bağlamı | Panele konuşmacı davet etmek |
| Alan | Kişilerin çalıştığı konu | Bilgisayarlı Görü |
| Konum | Tercih edilen şehir veya ülke | İstanbul |
| Hedef profil | Aranan kişinin **rolü** (etkinliğin konusu değil) | Akademisyen, Kurucu, Şef |
| Hedef aday sayısı | 1–1000. Bu sayıya ulaşılınca arama durur | 10 |
| Arama dili | Kaynakların dili; "Otomatik" çok dilli arar | Türkçe |
| Anahtar kelimeler | Virgülle ayrılır | computer vision, derin öğrenme |
| Notlar | Ekip içi notlar | — |

Konum ve dil **filtre değil, tercihtir.** Hedef sayıya yalnızca rolü uyan, konumu çelişmeyen ve
konu kanıtı olan kişiler sayılır. Diğerleri de inceleme için listelenir, ancak hedefe sayılmaz
(her türden en fazla hedef sayısı kadar). Hedef sayıya ulaşılması garanti değildir.

### Durumlar

| Kayıt | Durumlar |
| --- | --- |
| Araştırma | Yeni → Aranıyor → Kaynaklar okunuyor → Değerlendirmeye hazır → Tamamlandı. Arama aday bulamazsa "Aday bulunamadı", hatayla biterse "Sonuç alınamadı" |
| Aday | Yeni, İnceleniyor, Onaylı, Reddedildi, İletişime geçildi, Arşivlendi |

### Roller

| Rol | Yetki |
| --- | --- |
| Yönetici | Her şey, kullanıcı yönetimi dahil |
| Araştırmacı | Araştırma oluşturma, arama başlatma, adayları değerlendirme |
| İzleyici | Okuma ve dışa aktarma |

## Mimari

```text
Panel / n8n ──▶ backend (FastAPI) ──▶ PostgreSQL (veri + iş kuyruğu) ◀── worker ──▶ arama motorları
                                                                                    kaynak sayfalar
```

| Servis | Görev | Port (host) |
| --- | --- | --- |
| `db` | PostgreSQL 17: tüm veriler ve iş kuyruğu | `127.0.0.1:55432` (`DB_PORT`) |
| `backend` | REST API ve Jinja2 panel tek süreçte. Başlarken migration'ları uygular ve ilk yöneticiyi oluşturur | `127.0.0.1:8100` (API), `PANEL_BIND:3100` (panel) |
| `worker` | Kuyruktaki arama işlerini sırayla çalıştırır; 10 dakikada bir bakım yapar | — |

Backend ve worker aynı imajı kullanır. Docker Compose proje adı `relationship-intelligence`'dır.

### Arama hattı

Hattı `backend/app/services/collection.py` yönetir.

| Adım | Ne yapar | Modül |
| --- | --- | --- |
| 1. Gereksinim modeli | Rol, konu (eşanlamlılarıyla) ve konum | `requirements.py`, `topics.py` |
| 2. Keşif | Sorgu planını DDGS motorlarında sırayla dener | `discovery.py`, `search.py` |
| 3. Ön eleme | Sayfa türünü belirler; iş ilanı, tanım ve PDF sayfalarını atlar; aynı sitedeki ekip bağlantılarını izler | `triage.py` |
| 4. Okuma | robots.txt kurallarına uyar; SSRF korumalıdır; boyut ve süre sınırı vardır | `fetching.py` |
| 5. Çıkarım | Kişi listeleri, metin içindeki rol anmaları, sayfa sahibi ve şehir | `record_blocks.py`, `mentions.py`, `page_context.py`, `extraction.py` |
| 6. Eşleştirme ve puan | Rol, konu ve yer kararları; 0–100 arası puan | `matching.py`, `scoring.py` |
| 7. Tekilleştirme ve kayıt | Aynı kişiyi birleştirir, kaynakları ekler | `deduplication.py`, `candidates.py` |
| 8. Dışa aktarma | CSV, Excel, JSON, Google Sheets | `export.py` |

LinkedIn benzeri platformlar aranır ama sayfaları açılmaz. Arama sonucunun başlığındaki kişi
"Platform ipucu · doğrulanmadı" olarak eklenir (`platforms.py`).

Durum makineleri, idempotency, tekilleştirme kuralları ve hata biçimi:
[docs/architecture.md](docs/architecture.md).

## Veri modeli

Tüm veriler PostgreSQL'de, `relationship-intelligence_postgres_data` Docker volume'unda durur.

| Tablo | İçerik |
| --- | --- |
| `research_requests` | Formdaki tüm bilgiler ve araştırmanın durumu |
| `research_keywords` | Anahtar kelimeler, her biri ayrı satırda |
| `collection_jobs` | Her arama çalıştırması: sorgular, işlenen sayfa, eklenen/birleştirilen aday sayısı, süre ve hata |
| `source_documents` | Bulunan her sayfa: adres, başlık, sorgu, motor, sıra, sayfa türü, metin ve sonuç |
| `candidates` | Kişiler: ad, görev, kurum, konum, profil, puan, gerekçe (`match_details`) ve inceleme durumu |
| `candidate_sources` | Adayın kaynak sayfası ve o sayfadan alıntı |
| `export_jobs` | Dışa aktarma kayıtları |
| `audit_logs` | Kim, ne zaman, ne yaptı |
| `users`, `login_sessions` | Kullanıcılar ve oturumlar |

Kayıt kuralları:

- **Aday her sayfadan sonra kaydedilir.** Arama yarıda kesilse de bulunanlar kaybolmaz.
- **Aynı kişi iki kez kaydedilmez.** Başka bir sayfada tekrar bulunursa mevcut kayda yalnızca yeni
  kaynak eklenir.
- **İnceleme kararları korunur.** Onaylanmış veya reddedilmiş bir adayın bilgilerine otomatik arama
  dokunmaz; yalnızca yeni kanıt ekleyebilir. İncelenmemiş adaylarda yalnızca boş alanlar doldurulur.
- **Sayfa metinleri 90 gün sonra silinir** (`SOURCE_TEXT_RETENTION_DAYS`). Adres, başlık, durum ve
  özet (hash) kalır. Adaylar ve kaynakları otomatik silinmez.
- **Bir araştırma silindiğinde** ona bağlı işler, sayfalar, adaylar ve kaynaklar da silinir.

## Yapılandırma

Tüm ayarlar `.env` dosyasındadır. Şablon: [.env.example](.env.example).

### Temel ve güvenlik

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `APP_ENV` | `production` | `production` güvensiz ayarlarla başlamayı reddeder (aşağıya bakın) |
| `LOG_LEVEL` | `INFO` | JSON log seviyesi |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | üretilir | Veritabanı bilgileri |
| `DB_PORT`, `API_PORT`, `WEB_PORT` | 55432, 8100, 3100 | Host portları; DB ve API yalnızca 127.0.0.1'e bağlanır |
| `PANEL_BIND` | `127.0.0.1` | Panel ağa açılacaksa sunucunun özel IP'si |
| `SECRET_KEY` | üretilir | Oturum imzası; en az 32 rastgele karakter |
| `N8N_API_KEY` | üretilir | Otomasyon için Bearer anahtarı; en az 32 karakter |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | üretilir | İlk yönetici; yalnızca hesap yoksa kullanılır |
| `AUTH_REQUIRED` | `true` | `false` yalnızca tek kişilik yerel geliştirme içindir |
| `COOKIE_SECURE` | `false` | Panel HTTPS ile sunulduğunda `true` olmalı |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,backend,host.docker.internal` | Kabul edilen Host adları (DNS rebinding koruması). Ağa açarken sunucu adını veya IP'sini ekleyin |
| `ALLOWED_ORIGINS` | boş | Çapraz kaynaklı tarayıcı uygulamaları; panel için gerekmez |
| `ENABLE_API_DOCS` | `true` | `/docs` ve `/openapi.json` |
| `ENABLE_DEMO_DATA` / `DEMO_MODE` | `false` | Kurgusal demo verisi; production'da `false` olmalı |

`APP_ENV=production` iken backend ve worker şu durumlarda **başlamaz**: `AUTH_REQUIRED=false`,
SQLite veritabanı, `DEMO_MODE=true`, zayıf `SECRET_KEY`, `ALLOWED_ORIGINS=*` veya kısa
`N8N_API_KEY`. `COOKIE_SECURE=false` yalnızca uyarı olarak loglanır.

### Arama ve toplama

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `LIVE_SEARCH_ENABLED` | `true` | Canlı web aramasını açar veya kapatır |
| `SEARCH_BACKENDS` | `yahoo,duckduckgo,brave,google,mojeek,startpage` | Motorlar sırayla denenir; sonuç veren ilk motor iş boyunca öne alınır |
| `COLLECTION_TIME_BUDGET_SECONDS` | 3600 | Güvenlik tavanı. Arama; hedef sayıya ulaşınca, kullanıcı durdurunca veya yeni kaynak kalmayınca biter, en geç bu sürede |
| `COLLECTION_MAX_SOURCES` | 500 | İş başına en fazla kaynak |
| `COLLECTION_MAX_FOLLOWED_LINKS` | 30 | İş başına izlenen aynı site ekip/kadro bağlantısı |
| `SEARCH_PAUSE_SECONDS` | 2 | Sonraki sonuç sayfası sorgusundan önce bekleme. Tüm motorlar boş dönerse bu kadar beklenip bir kez daha sorulur |
| `SEARCH_QUERY_INTERVAL_SECONDS` | 1 | İlk sayfa sorguları arasındaki en kısa süre |
| `COLLECTION_MAX_ATTEMPTS` | 2 | Çökme veya kapanma sonrası otomatik devam hakkı |
| `COLLECTION_STALE_AFTER_SECONDS` | 300 | İşçiden bu süre sinyal gelmezse iş yeniden sıraya alınır |
| `DISCOVERY_RETRIES`, `FETCH_RETRIES`, `RETRY_BACKOFF_SECONDS` | 2, 1, 1.0 | Geçici hata tekrarları |
| `FETCH_TIMEOUT_SECONDS`, `FETCH_DOCUMENT_SECONDS`, `FETCH_MAX_BYTES` | 8, 20, 3 MiB | Sayfa okuma sınırları |

### Sınırlar ve saklama

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `SOURCE_TEXT_RETENTION_DAYS` | 90 | Sayfa metni bu süre sonunda silinir; 0 = kapalı |
| `MAX_CANDIDATES_PER_RESEARCH` | 5000 | Araştırma başına aday sınırı |
| `MAX_REQUEST_BYTES` | 5 MB | İstek gövdesi sınırı |
| `RATE_LIMIT_PER_MINUTE` | 600 | Oturum veya anahtar başına dakikalık istek |
| `LOGIN_ATTEMPTS_PER_MINUTE` | 10 | Hesap başına dakikalık giriş denemesi |

### İsteğe bağlı entegrasyonlar

| Değişken | Varsayılan | Açıklama |
| --- | --- | --- |
| `AI_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL` | `mock` | `/api/v1/ai/*` uçları. Arama hattı yapay zekâ gerektirmez |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | boş | Google Sheets dışa aktarma |

## Çalıştırma ve bakım

Komutlar Windows PowerShell içindir. Linux ve macOS'ta `.venv/Scripts/python.exe` yerine
`.venv/bin/python` kullanın; aynı işler `Makefile` hedefleriyle de yapılabilir (`make up`,
`make logs`, `make backup` ...).

### Günlük komutlar

```powershell
docker compose ps                        # servis durumu
docker compose logs -f backend worker    # JSON loglar; request_id ve job_id ile izlenebilir
docker compose stop                      # durdurur, veriler korunur
docker compose up -d                     # yeniden başlatır
```

> **Uyarı:** `docker compose down -v` veritabanı volume'unu siler ve tüm araştırma verisi kaybolur.
> Durdurmak için `stop` veya `down` (`-v` olmadan) kullanın.

Servisler `restart: unless-stopped` ile tanımlıdır; Docker Desktop açıldığında kendiliğinden başlar.

### Yedekleme

```powershell
.venv/Scripts/python.exe scripts/backup.py --verify
```

PostgreSQL yedeği (custom format, `pg_restore` ile açılır) `backups/` klasörüne yazılır. `--verify`
yedeği geçici bir veritabanına geri yükleyerek doğrular; çalışan veriye dokunmaz. `backups/` Git'e
eklenmez. Yedekleri düzenli alın ve başka bir cihaza kopyalayın.

### Sürüm güncelleme

Migration'lar yalnızca ekleme yapar ve mevcut veriyi korur. Puanlama yöntemi değiştiyse `rescore`
mevcut adayların puanını, gerekçesini ve eşleşme kararlarını yeniler; durum, not ve elle yapılan
düzenlemeler korunur.

```powershell
.venv/Scripts/python.exe scripts/backup.py --verify   # 1. yedek
docker compose ps                                     # 2. sırada veya çalışan arama işi olmamalı
docker compose build backend                          # 3. imajı oluştur
docker compose up -d --no-build --wait                # 4. yeniden başlat; migration otomatik çalışır
docker compose exec backend python -m app.manage rescore
```

Backend ve worker aynı imajı paylaşır. Bu yüzden önce `build backend`, ardından `up --no-build`
çalıştırın; `up --build` iki servisi aynı anda derlemeye çalışıp "image already exists" hatası
verebilir.

Migration'ları elle denetlemek için:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic check        # modeller ve migration'lar uyumlu mu
```

### Yönetici parolası kurtarma

```powershell
docker compose exec backend python -m app.manage reset-password admin@example.com
```

Parola etkileşimli olarak sorulur, komut geçmişine yazılmaz. Kullanıcının tüm oturumları kapanır.

## Production dağıtımı

1. `python scripts/init_env.py` çalıştırın. `.env` içinde `APP_ENV=production`,
   `AUTH_REQUIRED=true` ve `ENABLE_DEMO_DATA=false` olduğundan emin olun.
2. Paneli ekip ağına açacaksanız:
   - Önüne HTTPS sonlandıran bir ters vekil (Caddy, Nginx) koyun ve `COOKIE_SECURE=true` yapın.
   - `PANEL_BIND` değerini sunucunun özel IP'si yapın; kullanıcıların yazdığı alan adını veya
     IP'yi `ALLOWED_HOSTS`'a ekleyin.
   - Güvenlik duvarında yalnızca ekip ağına izin verin. API portu (8100) localhost'ta kalır.
3. `docker compose build backend` ve `docker compose up -d --wait` ile başlatın, ardından
   `scripts/production_check.py` ile kabul testini çalıştırın.
4. Günlük yedeği (`scripts/backup.py --verify`) zamanlayın ve yedekleri başka bir cihaza kopyalayın.
5. n8n kullanmıyorsanız `ENABLE_API_DOCS=false` yapın.

Loglar Docker tarafından döndürülür (servis başına 10 MB × 5 dosya).

**Desteklenen ölçek:** tek backend, tek worker ve PostgreSQL. Hız sınırı süreç içinde tutulduğu
için birden fazla backend kopyası çalıştırmayın. Worker sayısı artırılırsa satır kilitleri işleri
ayırır, ancak arama motorlarına giden yük de artar.

## Entegrasyonlar

### n8n

Uygulama n8n iş akışını kendisi çalıştırmaz; n8n aynı REST API'yi `N8N_API_KEY` Bearer anahtarıyla
çağırır. İstek sözleşmesi, idempotency anahtarları, hata kodları ve örnek gövdeler:
[docs/n8n.md](docs/n8n.md).

### Google Sheets

`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` ve `GOOGLE_REFRESH_TOKEN` tanımlanınca panelde
"Google Sheets" seçeneği görünür.

- Gerekli kapsamlar: `https://www.googleapis.com/auth/spreadsheets` ve
  `https://www.googleapis.com/auth/drive.file`.
- Tablo, yenileme anahtarının sahibi olan Google hesabında oluşturulur ve dışa aktaran kullanıcının
  e-postasıyla düzenleyici olarak paylaşılır.
- Değerler `RAW` modunda yazılır; formüller çalışmaz.
- Bilgiler tanımlı değilse sahte (mock) sağlayıcı yalnızca önizleme döndürür.

> **Not:** Google Sheets aktarımı gerçek bir Google hesabıyla henüz test edilmedi. İlk kullanımda bir
> deneme aktarımı yapın.

### Yapay zekâ (isteğe bağlı)

`AI_PROVIDER=openai` ve `OPENAI_API_KEY` tanımlanırsa `/api/v1/ai/interpret` ucu OpenAI kullanır.
Varsayılan `mock` sağlayıcıdır. Arama hattı yapay zekâya ihtiyaç duymaz.

## Geliştirme ve test

### Geliştirme ortamı

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv/Scripts/python.exe -r backend/requirements-dev.txt
.venv/Scripts/python.exe -m playwright install chromium
```

> **Önemli:** `docker-compose.yml` sabit bir proje adı (`relationship-intelligence`) tanımlar. Bu
> yüzden deponun başka bir kopyasında çalıştırılan `docker compose` komutları da gerçek kurulumu
> hedefler. Deneme kurulumlarında farklı bir proje adı (`docker compose -p <ad> ...`), ayrı bir
> `.env` ve farklı portlar kullanın.

### Testler

Birim ve entegrasyon testleri geçici bir SQLite veritabanında çalışır; API, kuyruk, işçi, çıkarım,
dışa aktarma ve güvenlik akışlarını kapsar.

```powershell
cd backend
../.venv/Scripts/python.exe -m pytest -q
../.venv/Scripts/python.exe -m ruff check .
```

Aynı testler gerçek PostgreSQL üzerinde (satır kilitleri ve veri tipleri için). Veritabanı adı
`test` içermelidir:

```powershell
docker run -d --name rip-test-pg -e POSTGRES_PASSWORD=testpass -e POSTGRES_USER=test -e POSTGRES_DB=test -p 127.0.0.1:15499:5432 --tmpfs /var/lib/postgresql/data postgres:17-alpine
$env:TEST_DATABASE_URL = "postgresql+psycopg://test:testpass@127.0.0.1:15499/test"
../.venv/Scripts/python.exe -m pytest -q
docker rm -f rip-test-pg
```

Windows'ta bazı portlar Hyper-V tarafından ayrılmış olabilir; port hatası alırsanız başka bir
port seçin.

### Uçtan uca ve kabul testleri

| Komut | Ne test eder |
| --- | --- |
| `scripts/e2e_collection.py` | Tarayıcıdan uçtan uca akış; geçici veritabanı ve kontrollü dış kaynaklar |
| `scripts/production_check.py` | Çalışan kuruluma karşı kabul testi; dış servis kullanmaz, kendi kayıtlarını siler |
| `scripts/production_check.py --live --restart-worker` | Gerçek web araması ve işçi yeniden başlatma |
| `scripts/panel_smoke.py` | Playwright ile panel akışı |
| `scripts/load_test_data.py` | `test-data/ornek-adaylar.json` kurgusal setini n8n anahtarıyla yükler |

`production_check.py` production ayarlarını (`AUTH_REQUIRED=true`) bekler; test kayıtları yazar ve
sonunda siler. Yeni bir kurulumda doğrudan çalıştırılabilir. Gerçek veri içeren bir kurulumda ise
`--project-name` ile ayrı bir deneme kurulumunu hedefleyin.

`backend/tests/fixtures/search_cases_100.json` altı dilde 60 olumlu ve 40 olumsuz kurgusal örnek
içerir; hepsi API → kuyruk → işçi → çıkarım → kayıt akışından geçer. Bu, kontrollü set doğruluğudur;
internet genelinde doğruluk garantisi değildir.

## Arama kalitesi

Ölçüm setleri gerçek kişi adları içerdiği için Git dışında, `artifacts/eval/` altında tutulur.

| Set | Klasör | Kullanım |
| --- | --- | --- |
| D1 | `artifacts/eval/` | Geliştirme seti |
| D1b | `artifacts/eval/heldout` | Kontrol seti (geliştirme sırasında birkaç kez kullanıldı) |
| D1c | `artifacts/eval/fresh` | Kodu çalıştırmadan etiketlenmiş 28 gerçek sayfa |

24 Ekim 2026 ölçümü (D1c):

- **İlk kör ölçüm:** listelenen 601 kişinin 392'si bulundu (%65,2 duyarlılık), kesinlik %93,1.
  Eski kod aynı sette 2 kişi buluyordu.
- **Bu setten öğrenilen iki hata düzeltildikten sonra:** 561/633 (%88,6), kesinlik %99,5. Bu artık
  kör bir ölçüm değildir; sonraki dürüst ölçüm için yeni bir set gerekir.

```powershell
.venv/Scripts/python.exe scripts/eval_extraction.py                         # D1
.venv/Scripts/python.exe scripts/eval_extraction.py artifacts/eval/fresh    # D1c

# Uçtan uca canlı arama; geçici SQLite kullanır, çalışan veriye dokunmaz.
# --backend ile başka bir sürümün backend klasörü aynı taleplerde karşılaştırılabilir.
.venv/Scripts/python.exe scripts/eval_search.py --briefs 1,3 --budget 420 --json out.json
```

Ayrıntılı denetim ve ölçüm geçmişi: [docs/search-audit.md](docs/search-audit.md).

## Proje yapısı

```text
search_automation/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI uygulaması ve güvenlik başlıkları
│   │   ├── api.py            # REST API (/api/v1)
│   │   ├── panel.py          # Panel sayfaları
│   │   ├── worker.py         # Arama işçisi
│   │   ├── manage.py         # Yönetim komutları: reset-password, rescore
│   │   ├── seed.py           # İlk yönetici ve demo verisi
│   │   ├── models.py         # Veritabanı modelleri
│   │   ├── schemas.py        # API şemaları
│   │   ├── core/             # Ayarlar, veritabanı, güvenlik, hız sınırı, idempotency, loglama
│   │   ├── services/         # Arama hattı, tekilleştirme, puanlama, dışa aktarma
│   │   ├── templates/        # Jinja2 panel şablonları
│   │   └── static/           # CSS, JavaScript, fontlar, logolar
│   ├── migrations/           # Alembic migration'ları
│   ├── tests/                # pytest
│   └── Dockerfile
├── scripts/                  # Kurulum, yedek, kabul testleri, kalite ölçümü
├── docs/                     # Mimari ve denetim belgeleri
├── test-data/                # Kurgusal örnek veri
├── backups/                  # Veritabanı yedekleri (Git dışı)
├── artifacts/                # Ölçüm setleri ve çıktılar (Git dışı)
├── frontend/                 # Eski Next.js arayüzü; kullanılmıyor
├── docker-compose.yml
├── Makefile
└── .env.example
```

### Panel teması

Panel İBTİKAR'ın görsel kimliğini (ibtikar.org.tr) izler:

- Renkler: lacivert `#091328` ve turuncu vurgu `#f84713`. Buton ve küçük yazılarda erişilebilir
  kontrast için `#d63907` / `#c22e00` kullanılır. Tüm renkler `backend/app/static/panel.css`
  başındaki değişkenlerdedir.
- Yazı tipleri: başlık ve etiketlerde Space Grotesk, metinde Inter, Arapçada IBM Plex Sans Arabic.
- Fontlar (`static/fonts`, OFL lisanslarıyla) ve logolar (`static/brand`) yerel olarak sunulur;
  güvenlik politikası (CSP) yalnızca kendi alan adından kaynak yüklenmesine izin verir. Logolar
  ibtikar.org.tr'den alınmıştır; resmi marka dosyaları aynı adlarla değiştirilebilir.

## Sorun giderme

| Belirti | Neden ve çözüm |
| --- | --- |
| `Invalid host header` (400) | Panele `ALLOWED_HOSTS` içinde olmayan bir adla erişiliyor. Adı veya IP'yi ekleyip `docker compose up -d` çalıştırın |
| Backend başlamıyor, logda `config.invalid` | `APP_ENV=production` ile güvensiz bir ayar var. Mesajdaki değişkeni düzeltin |
| Girişten sonra tekrar giriş ekranı açılıyor | HTTP üzerinden `COOKIE_SECURE=true` kullanılıyor. HTTPS kullanın veya yalnızca localhost'ta `false` bırakın |
| Arama "Sonuç alınamadı": kaynaklara erişilemedi | Arama motorları geçici olarak engelledi veya ağ yok. `docker compose logs worker` içinde `discovery.failed` olaylarına bakın, birkaç dakika sonra yeniden deneyin |
| Arama uzun süre "Sırada" kalıyor | Worker çalışmıyor. `docker compose ps worker` ve `docker compose logs worker` ile kontrol edin |
| Kaynak `FAILED`: "disallows automated retrieval" | Site robots.txt ile otomatik erişimi yasaklıyor; tasarım gereği atlanır |
| Kaynak `SKIPPED`: "Platform otomatik okumaya kapalı" | LinkedIn benzeri sayfalar açılmaz (tasarım gereği); başlıkta kişi varsa doğrulanmamış ipucu olarak eklenir |
| 429 "Too many requests" | Oturum başına dakikada 600 istek veya hesap başına 10 giriş denemesi aşıldı |
| 413 | İstek gövdesi `MAX_REQUEST_BYTES` sınırını aşıyor; toplu içe aktarmayı bölün |
| Hata mesajında "Hata kodu" var | `docker compose logs backend \| Select-String <kod>` ile tam hata izini bulun |

## Bilinen sınırlamalar

- **Ortak çalışma alanı:** Giriş yapan herkes tüm araştırmaları görür. Rol bazlı yetki vardır,
  talep bazlı paylaşım yoktur.
- **Ücretsiz arama:** Anahtarsız arama ticari bir hizmet garantisi (SLA) sunmaz; motorlar istekleri
  sınırlayabilir. Hedef sayıya ulaşılması garanti değildir. Lisanslı bir arama API'si
  `DiscoveryProvider` arayüzüyle eklenebilir.
- **Okunamayan içerik:** LinkedIn, ResearchGate gibi siteler otomatik okumayı engeller; bu kurallar
  aşılmaz. PDF, JavaScript ile oluşturulan sayfalar, bot doğrulaması isteyen siteler, oturum
  gerektiren içerik ve adları yalnızca görselde olan sayfalar okunamaz.
- **TLS:** Bazı ABD üniversite sitelerinde ara sertifika eksik olduğu için bağlantı kurulamaz.
- **Çıkarım:** Kurallı çıkarım her sayfa yapısını kapsamaz; ölçümler için
  [Arama kalitesi](#arama-kalitesi) bölümüne bakın. Rolü belirtilmemiş "konuşmacı" veya "uzman"
  aramaları en zayıf sonucu verir.
- **Konum çıkarımı:** Konum kişinin kendi kaydında yoksa sayfa sahibinin adresinden çıkarılır ve
  "sayfadan" diye işaretlenir; bu bir doğrulama değildir.
- **Tekilleştirme temkinlidir:** Farklı alt alan adlarında bulunan aynı kişi ayrı kayıt olarak
  kalabilir.
- **Kimlik doğrulama:** E-posta ile parola sıfırlama, SSO ve MFA yoktur.
- **Ölçek:** Hız sınırı ve tek worker tek sunucu için tasarlanmıştır.
- **Eski arayüz:** `frontend/` eski Next.js arayüzüdür; canlı toplamayı desteklemez, Compose'dan
  çıkarılmıştır ve bakımı yapılmaz.

## Belgeler

| Belge | İçerik |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Mimari, durum makineleri, idempotency, tekilleştirme, yetkilendirme |
| [docs/n8n.md](docs/n8n.md) | n8n entegrasyon sözleşmesi |
| [docs/search-audit.md](docs/search-audit.md) | Arama denetimi, yeniden tasarım ve ölçüm sonuçları |
| [docs/scraper-architecture.md](docs/scraper-architecture.md) | Sayfa toplama mimarisi kararı |
| [docs/mvp-readiness.md](docs/mvp-readiness.md) | Üretime hazırlık durumu ve doğrulama sonuçları |
| [docs/validation.md](docs/validation.md) | Doğrulama geçmişi |
