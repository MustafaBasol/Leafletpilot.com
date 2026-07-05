# LeafletPilot — Satılabilirlik Raporu

*Tarih: 4 Temmuz 2026 · Soru: Bu haliyle piyasada gider mi? Ne eklemek gerekir? Müşteri için kolay mı?*

---

## 1. Net Cevap: Bu haliyle satılmaz — ama satışa çok yakın bir çekirdek var

**Neden satılmaz:** Ürünün müşteriye verdiği söz "listeyi gönder, broşürü al". Bu zincirin üç kritik halkası henüz yok:

| Halka | Durum |
|---|---|
| Liste alma (Telegram/WhatsApp bot) | ❌ Yok — `BotConnections` sayfası statik mock, backend'de webhook yok |
| Broşür üretme (şablon → PDF/PNG render) | ❌ Yok — `ExportJob` sadece kayıt oluşturuyor, gerçek dosya üretilmiyor |
| Dosya gönderme | ❌ Yok — "Kullanıcıya Gönder" butonu placeholder |

Ayrıca ücretli müşteri almanın önkoşulları eksik: kimlik doğrulama yok (müşteri verisi izole edilemez), deployment yok (canlıya çıkılamaz), ödeme altyapısı yok (para tahsil edilemez).

**Neden yakın:** Zor kısımların önemli bölümü zaten çalışıyor:
- Ürün kataloğu + marka/kategori yönetimi (gerçek API'ye bağlı)
- Akıllı ürün eşleştirme motoru (fuzzy match, alternatif isimler, güven skoru — MVP hedefi %80+)
- Metinden kampanya oluşturma (`parse-text` / `from-text` çalışıyor)
- Kampanya iş akışı ve eşleştirme onay ekranları
- Temiz, kurumsal bir admin panel

Yani "motor" büyük ölçüde hazır; eksik olan müşterinin gördüğü iki uç: **giriş kanalı (bot)** ve **çıkış ürünü (broşür dosyası)**.

## 2. Ara Yol: Bugün satışa başlamanın yöntemi — "Concierge MVP"

`docs/design/11_MVP_SCOPE.md`'deki pilot hedefi (5 pilot market → 2 ücretli) tam otomasyon beklemeden başlatılabilir:

1. Müşteri listeyi normal WhatsApp'tan **sana** gönderir (bot yok, sen varsın).
2. Sen listeyi panele yapıştırırsın — parse + eşleştirme otomatik çalışır (bu kısım hazır).
3. Broşürü şimdilik Canva/Figma şablonuyla yarı elle üretirsin.
4. PDF/PNG'yi WhatsApp'tan geri gönderirsin.

**Faydası:** Gerçek müşteri talebini, fiyat kabulünü ve eşleştirme kalitesini ürün bitmeden test edersin; ilk gelir ve referans müşteriler render motoru gelmeden oluşur. Landing page'deki "ilk broşür ücretsiz" teklifi bu modelle bugün gerçek.

## 3. Satış İçin Eklenecek Özellikler (öncelik sıralı)

### P0 — Bunlar olmadan ürün "ürün" değil
1. **Şablon → PDF/PNG render motoru** (Phase 16). Öneri: HTML/CSS şablon + Playwright ile PDF/PNG. Çok ürün varsa otomatik sayfa bölme. Bu tek başına en yüksek öncelik — ürünün ta kendisi.
2. **Telegram bot akışı** (`docs/backend/05_TELEGRAM_MVP_PLAN.md` zaten planlı): metin listesi alma → önizleme gönderme → butonlu onay/revizyon → final dosya gönderme.
3. **Auth + gerçek tenancy**: JWT + parola hash; `market_id`'nin kimlikten türetilmesi (detaylar `docs/PROJE_INCELEME_RAPORU.md` §2). Ücretli müşteri verisi izole olmadan satış yapılamaz.
4. **Deployment**: Dockerfile + docker-compose + bir VPS/PaaS'a canlı kurulum + HTTPS. Telegram webhook'u için zaten public bir URL şart.

### P1 — İlk 10 müşteriye ölçeklenmek için
5. **Excel içe aktarma** — butonları UI'da zaten var, işlevsiz; esnafın elindeki liste çoğu zaman Excel.
6. **Ürün görseli yükleme + obje depolama (S3/R2)** — katalog operasyonunun kilidi.
7. **Basit abonelik/ödeme**: Stripe Checkout + plan limitleri (59/119/199€). İlk pilotlarda elle faturalama yeterli; 5+ müşteride otomasyona geç.
8. **Onboarding otomasyonu**: yeni market + katalog kurulum akışı (ilk 300 ürünlük hazır katalog şablonundan kopyalama — `11_MVP_SCOPE.md`'de kategori/marka listesi hazır).

### P2 — Büyüme
9. **WhatsApp Business API** — hedef kitle (Avrupa'daki Türk marketleri) asıl olarak WhatsApp kullanıyor; Telegram teknik kolaylık için ilk adım, WhatsApp asıl pazar kanalı.
10. Instagram Story formatı, çok dilli broşür (Almanca/Hollandaca pazarları), çoklu şube, gelişmiş raporlama.

## 4. Müşteri İçin Kolay Kullanılabilir mi?

**Kritik tespit:** Ürün ilkesi #1 "Kullanıcı panel öğrenmek zorunda kalmamalı" — ama bugün ürünün %100'ü panel. Yani mevcut arayüz **son müşteri için değil, operatör (sen) için**. Bu doğru bir kurgu; karışıklığı önlemek için netleştirilmeli:

- **Müşteri deneyimi = bot.** Esnaf yalnızca mesaj atar ve onaylar. Kolaylık çıtası: "WhatsApp kullanabilen herkes kullanabilmeli." Bot gelmeden müşteri deneyimi diye bir şey yok — concierge modelde "sen" botsun.
- **Panel = iç operasyon aracı.** Operatör açısından panel iyi durumda ama demo/satış sırasında güven zedeleyecek pürüzler var:
  - Dashboard tamamen sahte veri gösteriyor (müşteriye demo yaparken gerçek rakamlar görünmeli).
  - Filtreler ve bazı butonlar görsel ama işlevsiz — "tıkladım, olmadı" hissi demo öldürür.
  - Yıkıcı işlemlerde onay sorulmuyor (yanlış tıkla, ürün pasifleşsin — operatör hatası müşteri broşürünü bozar).
  - Ayarlar kaydedilmiyor ("kaydettim" diyor ama kaydetmiyor).

**Öneri:** Satış demosundan önce en azından şunlar düzeltilmeli: Dashboard'u gerçek veriye bağla, işlevsiz filtre/butonları kaldır veya çalıştır, onay diyalogları ekle. (Ayrıntılar `docs/PROJE_INCELEME_RAPORU.md` §4-5.)

## 5. Landing Page — Yapıldı ✅

`src/pages/Landing.jsx` olarak projeye eklendi (giriş yapmamış kullanıcı `leafletpilot.com`'u açınca bunu görür). Kurgu, teknik bilmeyen esnafı denemeye ikna etmek üzerine:

| Bölüm | İkna hedefi |
|---|---|
| Hero: "Ürün listenizi gönderin, broşürünüz dakikalar içinde hazır" + telefon mesajlaşma + broşür mockup'ı | 5 saniyede "bu ne işe yarar"ı göster |
| Acı noktaları: "Her hafta 2-6 saat Canva" | Problemi müşterinin kendi cümleleriyle tanı |
| Nasıl çalışır: 3 adım | "Benim yapabileceğim kadar basit" hissi |
| Özellik kartları | Katalog, eşleştirme, şablon, onay güveni |
| Fiyatlar: 59/119/199€ + "ilk broşür ücretsiz" | Şeffaflık + risksiz deneme |
| SSS + final CTA | İtirazları eritme, tek eylem: Ücretsiz Dene |

**Dönüşümü artırmak için sırada (kod dışı işler):**
- Gerçek broşür örneği: render motoru çıkınca hero'daki CSS mockup'ı gerçek çıktı görseliyle değiştir — en güçlü satış kanıtı budur.
- Sosyal kanıt: ilk pilot marketlerin adı/logosu + 1-2 cümlelik yorum ("X Market, haftada 4 saat kazanıyor").
- 30-60 saniyelik ekran kaydı video (liste gönder → broşür gelsin).
- CTA'nın hedefi şimdilik `#/login`; gerçek dünyada bir **demo talep formu veya WhatsApp linki** olmalı (esnaf form doldurmaz, mesaj atar: `wa.me/...` linki en düşük sürtünmeli kanal).
- SEO temelleri: `index.html`'e title/description meta, Almanca sürüm (pazar Avrupa ise).

## 6. Özet Karar Önerisi

1. **Bu hafta:** Concierge modelle 5 pilot market görüşmesi başlat (demo mesajı `11_MVP_SCOPE.md`'de hazır). Landing page + panel demosu bunun için yeterli.
2. **Paralelde geliştirme sırası:** Render motoru → Telegram bot → Auth → Deployment. (Ayrıntılı sıra: `docs/YOL_HARITASI.md`.)
3. **Satış kanıtı biriktikçe:** landing'e gerçek broşür görselleri ve müşteri yorumları ekle; Stripe ile ödemeyi otomatikleştir.

*İlgili dosyalar: `docs/PROJE_INCELEME_RAPORU.md` (teknik/güvenlik detayı), `docs/YOL_HARITASI.md` (uygulama sırası), `src/pages/Landing.jsx` (landing page).*
