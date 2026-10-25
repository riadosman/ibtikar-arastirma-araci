# Test verileri

Panel: http://localhost:3100 (bu kurulumda giriş kapalı: `AUTH_REQUIRED=false`).

## A. Hazır kurgusal veri (internet gerekmez)

```powershell
.venv/Scripts/python.exe scripts/load_test_data.py
```

"TEST — Örnek veri (silinebilir)" araştırmasını ve 12 kurgusal kaydı yükler. Beklenen sonuç:
**9 yeni aday, 3 birleştirme.** Tekrar çalıştırmak çift kayıt oluşturmaz.

| Kayıtlar | Beklenen | Neyi test eder |
| --- | --- | --- |
| Leyla Haddad + Dr. Leyla Haddad | Tek aday, 2 kaynak | Aynı kişisel e-posta, unvanlı isim |
| Emre Yıldırım + EMRE YILDIRIM | Tek aday, 2 kaynak | Türkçe karakter (ı/ö/ü) + aynı kurum |
| Omar Khaled + Omar Abdullah Khaled | Tek aday, 2 kaynak | Aynı LinkedIn profili (tr. alt alan adı, alt sayfa), göbek adı |
| Selin Aksoy + Burak Demir | İki ayrı aday | Ortak `info@` adresi ve şirket LinkedIn sayfası kimlik sayılmaz |
| Ahmed Hassan ×2 | İki ayrı aday | Aynı isim, farklı kişisel e-posta = farklı kişiler |
| سارة المصري | Tek aday | Arapça isim ve kanıt metni |
| Formül Testi | Tek aday | Dışa aktarmada `=HYPERLINK(...)` ve `+Örnek Kurum` formül olarak çalışmamalı |

Panelde denenecekler:

1. Aday sayfası: "Neden önerildi?" (puan kırılımı), kaynaklar ve kanıt cümleleri, ilk/son görülme tarihi.
2. Birkaç adayı **Onaylı**, birini **Reddedildi** yapın; not ekleyin.
3. Profili düzenle: e-posta veya kurum değiştirin, puanın yeniden hesaplandığını görün.
4. Filtre: durum = Onaylı; isim araması "Ahmed".
5. Dışa aktarma: CSV ve Excel; önce yalnızca onaylılar, sonra **Tüm adaylar** işaretli. Excel'de
   "Formül Testi" satırındaki değerler düz metin olmalı.
6. Bitince araştırmayı silin (silme yalnızca giriş açıkken yöneticiye özeldir; bu kurulumda herkes silebilir).

## B. Canlı web araması senaryoları

"Yeni araştırma" formuna girin, kaydedin, **Web'de ara**. Sonuçlar dış arama motorlarına bağlıdır;
aynı arama farklı zamanlarda farklı sonuç verebilir. Arama yeni kişi buldukça genişleyerek sürer; 1 dakika boyunca yeni kişi çıkmazsa durur (en fazla ~10 dakika).

| # | Başlık | Alan | Konum | Hedef profil | Adet | Dil | Anahtar kelimeler | Beklenen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Görüntü işleme akademisyenleri | Computer Vision | Istanbul | Professor | 5 | İngilizce | computer vision, faculty | Üniversite profil sayfalarından akademisyenler (8 Ekim testinde 3 kişi bulundu) |
| 2 | Türkçe NLP uzmanları | Doğal dil işleme | İstanbul | Akademisyen | 5 | Türkçe | doğal dil işleme | Türkçe akademik sayfalar; kısmi sonuç olabilir |
| 3 | Yapay zekâ girişim kurucuları | Teknoloji | İstanbul | Kurucu | 5 | Türkçe | yapay zeka, girişim (Açıklama: "CTO veya kurucu arıyoruz") | Şirket ekip sayfaları; iş ilanları elenir |
| 4 | Arapça konuşan AI araştırmacıları | Artificial Intelligence | Istanbul | Professor | 5 | Arapça | Arabic NLP | Az sonuç veya `NO_RESULTS` olabilir (Arapça kaynak azlığı) |
| 5 | Belirsiz hedef | Gastronomi | Türkiye | Şef | 3 | Otomatik | yemek yarışması jüri | Önce ana sorgular, hedefe ulaşılmazsa otomatik "alternatif sorgular" |

Her aramada kontrol edin:

- Canlı ilerleme: kaynak akışı, bulunan adaylar, geçen süre; sayfadan çıkıp dönünce devam ediyor.
- **Aramayı durdur**: arama sürerken basın → "İptal edildi"; bulunan adaylar korunur.
- Aynı araştırmada ikinci kez **Web'de ara**: mevcut adaylar çoğalmaz, onayladıklarınız değişmez.
- "Son toplama işlemi" kartı: sorgu/sonuç/tekrar eden adres sayıları ve her kaynağın durumu
  (LinkedIn/ResearchGate gibi siteler robots kuralı nedeniyle "Erişilemedi" görünür — beklenen davranış).

## C. n8n / API ile içe aktarma

`ornek-adaylar.json` içindeki `candidates` dizisi doğrudan
`POST /api/v1/research-requests/{id}/candidates/bulk` gövdesi olarak kullanılabilir
(`Authorization: Bearer <N8N_API_KEY>`, `Idempotency-Key: <sabit değer>`). Ayrıntılar: `docs/n8n.md`.

Tüm kişi ve kaynaklar kurgusaldır; kaynaklar ayrılmış `example.com/.org/.net` alan adlarındadır.
