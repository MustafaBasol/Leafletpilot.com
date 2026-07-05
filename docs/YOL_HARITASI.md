# LeafletPilot — Yol Haritası

*Güncelleme: 4 Temmuz 2026 · Bu dosya projenin "sıradaki iş ne?" sorusunun tek cevabıdır. Her faz bittiğinde durumu güncelle.*

## Kuzey Yıldızı

> Market sahibi Telegram'dan ürün listesini gönderir; 5 dakika içinde onaylanmış, baskıya hazır broşür PDF'i ve sosyal medya görseli elinde olur.

Her yeni iş şu soruyla test edilir: **"Bu, yukarıdaki cümleyi gerçekleştirmeye yaklaştırıyor mu?"** Yaklaştırmıyorsa ertelenir.

## Mevcut Durum (özet)

- ✅ Backend: katalog + kampanya + eşleştirme + şablon API'leri, Alembic, seed, testler (Phase 5-15)
- ✅ Frontend: panel gerçek API'ye bağlı (kampanya, katalog, şablon), landing page
- ❌ Render motoru, Telegram bot, auth/tenancy, deployment, ödeme
- 📄 Detay: `docs/SATILABILIRLIK_RAPORU.md`, `docs/PROJE_INCELEME_RAPORU.md`

---

## Faz A — Broşür Render Motoru (P0, sıradaki iş)

**Amaç:** Kampanyadan gerçek A4 PDF + PNG üretmek. Ürünün ta kendisi.

- [ ] HTML/CSS tabanlı şablon yapısı (mevcut `Template` modeli üzerine; 2 hazır şablonla başla)
- [ ] Playwright ile HTML → PDF ve PNG render servisi (`backend/app/services/rendering.py`)
- [ ] Çok ürün varsa otomatik sayfa bölme
- [ ] `ExportJob`'ı gerçek üretime bağla: `queued → processing → completed/failed`
- [ ] Üretilen dosyayı diske/obje depolamaya yaz, `CampaignFile.storage_key` doldur, indirme endpoint'i
- [ ] Panelde gerçek önizleme (`PreviewFrame` placeholder'ının yerine)

**Bitti sayılır:** Panelden bir kampanya için "Dosya Üret" denince gerçek, açılabilir bir A4 PDF ve PNG iniyor.

## Faz B — Telegram Bot MVP (P0)

**Amaç:** Müşterinin paneli hiç görmeden broşür alması. Plan: `docs/backend/05_TELEGRAM_MVP_PLAN.md`

- [ ] `BotConnection` modeli + webhook endpoint'i (`/webhooks/telegram/...`)
- [ ] Gelen metin listesini `from-text` akışına bağla (parser hazır)
- [ ] Eşleşmeyen ürün raporunu mesajla bildir
- [ ] Önizleme PNG'sini gönder + butonlu onay/revizyon akışı
- [ ] Onay sonrası final PDF/PNG gönderimi
- [ ] Panel `BotConnections` sayfasını gerçek veriye bağla

**Bitti sayılır:** `11_MVP_SCOPE.md`'deki demo listesi Telegram'dan gönderilince, onay sonrası PDF telefondan iniyor.

## Faz C — Auth + Tenancy + Deployment (P0, canlıya çıkış)

**Amaç:** Ücretli müşteri verisini güvenle taşıyabilmek. Detay: `docs/PROJE_INCELEME_RAPORU.md` §2, `docs/backend/07_AUTH_AND_TENANCY_PLAN.md`

- [ ] JWT auth + parola hash (passlib/argon2), `/auth/login`, `/auth/me`
- [ ] `market_id`'yi `X-Market-Id` header'ından değil kimlikten türet; üyelik doğrula (IDOR kapanır)
- [ ] Rol kontrolü (izin matrisi: `07_AUTH_AND_TENANCY_PLAN.md`)
- [ ] CORS sıkılaştır, `DEBUG=false`, güvenlik header'ları
- [ ] Frontend: gerçek login, korumalı isteklerde token
- [ ] Dockerfile + docker-compose (backend, frontend, Postgres)
- [ ] VPS/PaaS'a kurulum + HTTPS + domain (Telegram webhook için de gerekli)
- [ ] GitHub Actions: push'ta backend pytest + frontend build

**Bitti sayılır:** `https://leafletpilot.com` canlı; iki farklı market hesabı birbirinin verisini göremiyor.

## Faz D — Operasyon Cilası (P1)

**Amaç:** Demo ve günlük operasyonda güven veren panel.

- [ ] Excel içe aktarma (butonlar UI'da hazır, işlevsiz)
- [ ] Ürün görseli yükleme + S3/R2 obje depolama
- [ ] Dashboard'u gerçek verilere bağla (mock kaldır)
- [ ] Yıkıcı işlemlere onay diyaloğu (ürün pasifleştirme, kampanyadan çıkarma)
- [ ] İşlevsiz filtre/butonları çalıştır veya kaldır
- [ ] Settings'i gerçekten kaydet
- [ ] Sessiz mock-fallback'i kaldır (hata hatadır)

## Faz E — Gelir Altyapısı (P1)

- [ ] Stripe Checkout + aylık abonelik (59/119/199€)
- [ ] Plan limitleri (kampanya/ay) uygulaması
- [ ] Yeni market onboarding akışı (hazır 300 ürünlük katalog şablonundan kopyalama)
- [ ] Landing: gerçek broşür görselleri + pilot müşteri yorumları + WhatsApp demo linki

## Faz F — Büyüme (P2)

- [ ] WhatsApp Business API (asıl pazar kanalı)
- [ ] Instagram Story formatı, gelişmiş şablonlar
- [ ] Çok dilli broşür (DE/NL), çoklu şube
- [ ] Raporlama ekranı, i18n altyapısı, react-router/react-query geçişi

---

## Geliştirmeye Paralel Satış İşleri (kod gerektirmez)

- [ ] 5 pilot market görüşmesi (demo mesajı: `docs/design/11_MVP_SCOPE.md` §Pilot Müşteri Planı)
- [ ] Concierge model: bot hazır olana kadar listeler WhatsApp'tan elle alınır, panel + yarı elle üretimle broşür teslim edilir
- [ ] Hedef: 5 pilottan 2 ücretli dönüşüm; her pilottan eşleştirme kalitesi geri bildirimi

## Çalışma Kuralları

1. Fazlar sıralıdır; A bitmeden B'ye başlama (Telegram botu gönderecek dosya olmadan anlamsız).
2. Her faz sonunda bu dosyadaki kutuları işaretle ve `docs/backend/08_IMPLEMENTATION_PHASES.md` ile senkron tut.
3. Yeni özellik fikri gelirse önce buraya P2 altına yaz; sıra bozulmaz.
4. Güvenlik maddeleri (Faz C) canlıya çıkmadan pazarlanamaz — internete açılmadan önce Faz C zorunlu.
