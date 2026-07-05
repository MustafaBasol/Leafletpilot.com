# LeafletPilot — Proje İnceleme Raporu

*Tarih: 4 Temmuz 2026 · Kapsam: backend (FastAPI), frontend (React), dokümantasyon ve proje altyapısı*

---

## 1. Yönetici Özeti

LeafletPilot; marketler, kasaplar ve şarküteriler için haftalık ürün/fiyat listesinden broşür üreten bir B2B SaaS. Mevcut durum: **temiz mimariye sahip, dürüst dokümante edilmiş bir MVP/demo** — katmanlı backend (routes/services/models/schemas), mock↔gerçek API geçişi olan düzenli bir frontend, Alembic migration'ları ve makul bir test iskeleti var.

Ancak proje **şu haliyle üretime (internete) açılamaz**:

1. **Hiç kimlik doğrulama yok** — tüm endpoint'ler herkese açık.
2. **Tenancy sahte** — istemcinin gönderdiği `X-Market-Id` header'ı doğrulamasız kabul ediliyor; herhangi biri herhangi bir marketin verisini okuyup değiştirebilir.
3. **Deployment altyapısı yok** — Dockerfile, CI, üretim yapılandırması hiç yok.
4. Ürünün asıl vaadi olan çekirdek özellikler (Telegram, PDF/PNG üretimi, dosya yükleme) henüz **placeholder**.

Aşağıda güvenlik açıkları, eklenmesi/çıkarılması gerekenler ve kullanılabilirlik önerileri öncelik sırasıyla, dosya referanslarıyla listelenmiştir. En sonda sıralı bir yol haritası var.

---

## 2. Güvenlik Açıkları ve Yapılması Gerekenler

### 2.1 KRİTİK — Kimlik doğrulama hiç yok

**Durum:**
- `backend/app/api/router.py` yalnızca `campaigns`, `catalog`, `templates`, `health` router'larını mount ediyor. `docs/backend/02_API_CONTRACTS.md`'de tanımlı `/auth/mock-login` ve `/auth/me` dahil hiçbir auth endpoint'i yok.
- `backend/app/models/user.py:21`'deki `password_hash` kolonu hiçbir yerde okunup yazılmıyor; `pyproject.toml`'da hash kütüphanesi (bcrypt/argon2/passlib) yok. Seed kullanıcısı `password_hash=None` ile oluşturuluyor (`backend/scripts/seed_dev_data.py`).
- Sonuç: sunucuya erişen herkes tüm kampanya, ürün, marka, kategori ve şablonları listeleyebilir, oluşturabilir, silebilir.

**Yapılacaklar:**
- [ ] JWT veya session tabanlı auth ekle (FastAPI için `fastapi-users` veya elle JWT + `python-jose`/`pyjwt`).
- [ ] Parola hash'leme için `passlib[argon2]` veya `bcrypt` ekle; login/register akışını yaz.
- [ ] Tüm route'lara auth dependency'si zorunlu kıl (health hariç).
- [ ] Frontend'de gerçek login akışı: `Login.jsx` şu an kimlik bilgilerini tamamen yok sayıyor ve koşulsuz `onLogin` çağırıyor.

### 2.2 KRİTİK — Sahte tenancy: `X-Market-Id` header'ı ile IDOR

**Durum:**
- `backend/app/api/deps.py:10-23` — `get_current_market_id` istemcinin gönderdiği `X-Market-Id` header'ını olduğu gibi döndürüyor; yalnızca boş olup olmadığına bakılıyor. Çağıranın o markete erişim yetkisi olup olmadığı doğrulanmıyor.
- Yani bir istemci header'a **herhangi bir market UUID'si** yazarak o kiracının tüm verisine tam okuma/yazma erişimi elde eder. Bu, projenin kendi kuralını da ihlal ediyor (`docs/backend/07_AUTH_AND_TENANCY_PLAN.md:143-144`: "Client'ın gönderdiği marketId, authenticated erişimi override etmemeli").
- Frontend tarafında market UUID'si `VITE_DEMO_MARKET_ID` env değişkeniyle geliyor (`src/api/config.js`) — `VITE_*` değişkenleri **build sırasında client bundle'a gömülür**, yani yayınlanan JS'te herkese görünür olur.
- Olumlu not: servis katmanındaki market filtrelemesi (`services/campaign.py`, `services/catalog.py`) doğru yazılmış; veri modeli tenant-aware. Eksik olan kimlik doğrulama katmanı.

**Yapılacaklar:**
- [ ] `market_id`'yi header'dan değil, **authenticated kullanıcının kimliğinden** türet.
- [ ] Kullanıcının `MarketUser` üyeliğini doğrula; üye olmadığı markete erişimde 403 döndür.
- [ ] Cross-tenant izolasyon testleri ekle (A marketinin kullanıcısı B marketinin kampanyasını görememeli).

### 2.3 YÜKSEK — Rol/yetki (authorization) kontrolü yok

**Durum:** `docs/backend/07_AUTH_AND_TENANCY_PLAN.md`'de platform_admin / market_admin / market_staff / operator rolleri ve modül bazlı izin matrisi tanımlı; `MarketUser.role` alanı modelde var ama **hiçbir route veya serviste denetlenmiyor**.

**Yapılacaklar:**
- [ ] Rol kontrolü yapan bir dependency yaz (ör. `require_role("market_admin")`) ve izin matrisine göre route'lara uygula.
- [ ] Özellikle yıkıcı endpoint'lere (DELETE `/catalog/brands/{id}`, `/catalog/products/{id}`, `/campaigns/{id}`) admin rolü şartı koy.

### 2.4 YÜKSEK — CORS yapılandırması kırılgan

**Durum:** `backend/app/main.py:18-24` — `allow_credentials=True` + `allow_methods=["*"]` + `allow_headers=["*"]`. Origin'ler şimdilik localhost ile sınırlı (`config.py:20`) ama `BACKEND_CORS_ORIGINS` genişletilirse (özellikle `*` yapılırsa) credentials ile birlikte ciddi bir açık oluşur.

**Yapılacaklar:**
- [ ] Method ve header listesini ihtiyaca daralt.
- [ ] Config'e "origin `*` ise `allow_credentials=False`" koruması ekle; üretim origin'lerini açıkça listele.

### 2.5 ORTA — Debug modu ve üretim sertleştirmesi eksik

**Durum:**
- `backend/.env` ve `backend/.env.example` `DEBUG=true` içeriyor. Kod varsayılanı `debug=False` (`config.py:18`) — bu iyi — ama örnek dosyanın debug'ı teşvik etmesi, deployment'ta traceback sızıntısı riski yaratır.
- HTTPS zorlaması, güvenlik header'ları (HSTS, X-Content-Type-Options), `TrustedHostMiddleware` yok. `index.html`'de CSP meta yok.

**Yapılacaklar:**
- [ ] `.env.example`'da `DEBUG=false` yap; üretim yapılandırmasında `ENVIRONMENT=production` zorunlu kıl.
- [ ] Güvenlik header middleware'i ekle (ör. `secure` paketi veya elle middleware).

### 2.6 ORTA — Rate limiting ve girdi sınırı yok

**Durum:**
- Hiçbir endpoint'te throttling yok. `parse-text` (`routes/campaigns.py:75-90`) uzunluk sınırı olmayan serbest metin kabul ediyor.
- Fuzzy eşleştirme endpoint'leri (`campaigns.py:203-241`) ürün başına Python tarafında `SequenceMatcher` skorlaması yapıyor — auth'suz haliyle ucuz bir DoS vektörü.

**Yapılacaklar:**
- [ ] `slowapi` veya reverse-proxy seviyesinde rate limit ekle (öncelik: yazma ve eşleştirme endpoint'leri).
- [ ] `parse-text` girdisine karakter limiti koy (Pydantic `max_length`).

### 2.7 ORTA — Frontend auth durumu localStorage boolean'ı

**Durum:** `src/App.jsx:51-69` — oturum, `localStorage["leafletpilot_mock_auth"] = "true"` değerinden ibaret. Kolayca taklit edilebilir ve XSS ile okunabilir. (Şimdilik mock olduğu için bilinçli; gerçek auth gelince bu desen kullanılmamalı.)

**Yapılacaklar:**
- [ ] Gerçek auth geldiğinde token'ı httpOnly cookie'de tut veya en azından kısa ömürlü access token + refresh akışı kullan; boolean bayrak desenini kaldır.

### 2.8 Olumlu güvenlik notları (mevcut iyi durumlar)

- **SQL injection riski düşük:** tüm sorgular SQLAlchemy 2.0 ORM + bound parametre; `text()` kullanımları sabit string (`health.py:28`, index tanımları).
- **Secret commit edilmemiş:** `.env` dosyaları gitignore'da ve takip edilmiyor; commit'lenmiş tek env dosyası zararsız `backend/.env.example`. Kaynak kodda API anahtarı/parola yok.
- **XSS bulunamadı:** `dangerouslySetInnerHTML`, `innerHTML`, `eval` hiç kullanılmamış; tüm render JSX-escaped.
- **Pagination sınırlı:** `limit` 1-100 arası, `offset >= 0` (`catalog.py:22-23`, `campaigns.py:46-47`).
- **Soft delete:** katalog silmeleri `is_active=False` yapıyor — veri kaybı riskini azaltıyor.

---

## 3. Eklenmesi Gerekenler

### 3.1 Üretim engelleyiciler
1. **Auth + gerçek tenancy** (bkz. §2.1–2.3) — her şeyden önce bu.
2. **Deployment altyapısı:** Repo'da hiç `Dockerfile`, `docker-compose.yml`, CI (`.github/` yok), nginx yapılandırması yok. Docs'taki "Phase 13: Deployment Planning" bölümü hiç uygulanmamış.
   - [ ] Backend + frontend + Postgres için docker-compose; üretim Dockerfile'ları.
   - [ ] GitHub Actions: her PR'da backend pytest + frontend build/validate çalıştır.
3. **Test altyapısını çalışır hale getir:** DB'ye bağlı backend testleri `TEST_DATABASE_URL` tanımlı değilse skip ediliyor; frontend'de hiç unit test yok (sadece `scripts/smoke-vite.mjs`). CI'da test Postgres container'ı ile testleri gerçekten çalıştır; frontend'e Vitest ekle.

### 3.2 Sağlamlık / gözlemlenebilirlik
- [ ] **Global exception handler:** beklenmeyen hatalar şu an ham 500 (debug'da traceback) dönüyor. Tutarlı bir hata zarfı ekle.
- [ ] **Yapılandırılmış loglama:** `core/logging.py` yalnızca `basicConfig`. JSON log + request logging ekle.
- [ ] **Audit logging:** `ActivityLog` modeli var ama hiçbir servis yazmıyor. Kampanya onayı, manuel eşleştirme, silme gibi işlemlerde aktör + market logla (07_AUTH_AND_TENANCY_PLAN.md:145'in gereği).

### 3.3 Ürün özellikleri (docs'ta vaat edilen ama eksik olanlar)
Bunlar MVP dokümanlarında (`docs/design/11_MVP_SCOPE.md`, `05_TELEGRAM_MVP_PLAN.md`, `06_FILE_STORAGE_AND_EXPORT_PLAN.md`) çekirdek olarak tanımlı, ancak kodda yok:
- [ ] **Telegram entegrasyonu:** webhook route'u, `BotConnection` modeli yok; `Conversation`/`IncomingMessage` modelleri var ama hiçbir route kullanmıyor. `BotConnections.jsx` sayfası tamamen statik mock.
- [ ] **PDF/PNG render ve önizleme (Phase 16):** `CampaignFile`/`ExportJob` yalnızca metadata kaydı; gerçek render (Playwright/HTML→PDF) ve `/preview`, `/approve`, `/request-revision` aksiyonları yok. Frontend'de `PreviewFrame` placeholder, `createExportJob` `requested_formats: ["placeholder"]` gönderiyor.
- [ ] **Dosya yükleme + S3/obje depolama:** hiç upload endpoint'i yok; frontend'deki Excel içe aktarma butonları ve ürün görseli yükleme alanları işlevsiz ("Bu fazda dosya işlenmez").
- [ ] **Eksik sayfalar:** `/markets`, `/files`, `/reports` sidebar'da var ama jenerik `PlaceholderPage` stub'ına düşüyor. Dashboard tamamen mock veri gösteriyor (hiç API çağrısı yapmıyor) — gerçek `/markets/{id}/dashboard` endpoint'i de backend'de yok.
- [ ] **Settings kalıcılığı:** `Settings.jsx` "Kaydet" yalnızca yerel bir bayrak set ediyor; backend'de `/settings` endpoint'i yok.

### 3.4 Kullanıcı güvenliği (UI)
- [ ] **Yıkıcı aksiyonlara onay diyaloğu — hiç yok:**
  - `ProductCatalog.jsx:412` ürün Aktif/Pasif geçişi anında uygulanıyor.
  - `CampaignDetail.jsx:300` "Kampanyadan Çıkar" onaysız siliyor.
  - `MissingProductModal.jsx:49` "Kampanyadan çıkar" (danger buton) onaysız.
  - `Templates.jsx` şablon durum değiştirme / varsayılan yapma anında.
  - Ortak bir `ConfirmDialog` bileşeni ekleyip bu noktalara uygula.

---

## 4. Çıkarılması / Düzeltilmesi Gerekenler

1. **Ölü kod:** `src/api/campaignApi.js` içindeki `createCampaign`, `updateCampaign`, `cancelCampaign`, `listCampaignFiles` hiçbir yerden çağrılmıyor — ya bağla ya kaldır.
2. **Sessiz mock fallback:** `Campaigns.jsx:35`, `Templates.jsx:20`, `TemplateDetail.jsx:28` — API hatasında sessizce mock veriye düşüp uyarı gösteriyor. Bu, gerçek bir kesintiyi sahte veriyle maskeleyebilir. `ProductCatalog` ve `CampaignDetail`'deki gibi "boş + açık hata" desenine geçir.
3. **Dekoratif (işlevsiz) kontroller:** ya işlevsel yap ya kaldır — kullanıcıda "çalışıyor" beklentisi yaratıyorlar:
   - `Campaigns.jsx:62-68` filtre chip'leri (Durum/Market/Kanal/Tarih/Eksik ürün) — handler'ı yok.
   - `Templates.jsx:77-81` FilterBar/chip'ler dekoratif.
   - `Settings.jsx:48-50` `SelectPlaceholder`'lar salt görsel.
   - `TemplateDetail.jsx:49-52` dört aksiyon da (Varsayılan Yap / Önizleme / Kopyala / Düzenle) sadece mesaj basıyor.
   - `NewCampaign.jsx:135` "Taslak Kaydet" gerçekte kaydetmiyor; başlıktaki "Önizleme Oluştur" sihirbazı atlayıp `setStep(5)` yapıyor.
4. **Dokümantasyon tutarsızlıkları:**
   - `docs/backend/08_IMPLEMENTATION_PHASES.md` Phase 14 bölümünü atlıyor (13 → 15), oysa git'te "Phase 14" commit'i var — dokümanı gerçek geçmişle senkronla.
   - Doc'taki "Phase 13: Deployment Planning" başlığı, gerçekte yapılan Phase 13 işiyle (frontend API mode) uyuşmuyor.
   - `docs/frontend/API_INTEGRATION.md` örneği `VITE_USE_REAL_API=false` derken diskteki `.env.local` `true` — repo'yu ilk çalıştıran kişi canlı backend olmadan her sayfada hata/fallback görür. Dokümana "önce backend'i + seed'i çalıştır" notu ekle.
   - `.gitignore`'da Python/frontend ignore blokları mükerrer (zararsız, temizlenebilir).

---

## 5. Kullanılabilirlik Önerileri

### Hızlı kazanımlar
1. **Onay diyalogları** (bkz. §3.4) — en yüksek etki/maliyet oranı.
2. **Loading göstergeleri:** yükleme durumları düz `<p>` metni; basit bir spinner/skeleton bileşeni tüm sayfalarda tutarlılık sağlar. Dashboard'a da loading/error durumu ekle (şu an hiç yok).
3. **Form validasyonu:**
   - `ProductCatalog` ürün modalında hiç client-side validasyon yok — tamamen backend 422 mesajına bağımlı. Zorunlu alan + fiyat formatı kontrolü ekle.
   - `NewCampaign`'de para birimi ve dil serbest metin `Input` — bunları select yap.
   - `Login`'de e-posta format kontrolü yok.
4. **Modal erişilebilirliği:** `Modal.jsx`'te `role="dialog"` ve `aria-modal` var (iyi) ama **focus trap, Esc ile kapatma, backdrop tıklamasıyla kapatma ve odak iadesi yok**. Bunları ortak Modal bileşenine bir kez ekle.

### Orta vadeli
5. **Responsive tablolar:** Kampanyalar tablosu 9, eşleştirme tablosu 10 kolon — mobilde taşar. Tabloları `overflow-x: auto` sarmalayıcıya al veya mobilde kart görünümüne geç. Sidebar'a mobil hamburger/drawer ekle (şu an yalnızca iki breakpoint var: 1100px ve 760px).
6. **i18n altyapısı:** tüm stringler JSX içine ve `dataSource.js` label haritalarına gömülü Türkçe. `docs/design/12_COPY_I18N.md` var ama runtime i18n yok. Büyümeden önce `i18next` gibi bir çatıya taşımak, sonradan taşımaktan çok daha ucuz. "Dil" alanları şu an dekoratif.
7. **Router:** elle yazılmış hash-router (`App.jsx` içindeki if-merdiveni) yerine `react-router` — nested route, 404, kod bölme ve tarayıcı geçmişi desteği için. (Acil değil; sayfa sayısı artmadan yapılmalı.)
8. **Veri katmanı:** her sayfa mount'ta yeniden fetch ediyor, önbellek/paylaşım yok. `@tanstack/react-query` eklemek hem önbellek hem loading/error durumlarını standartlaştırır.
9. **Erişilebilirlik detayları:** özel buton-tabanlı seçiciler ve şablon kartlarına `aria-pressed`/`aria-selected`; sayfaya skip-link.

---

## 6. Önerilen Yol Haritası

### Aşama A — Üretim engelleyiciler (internete açmadan önce şart)
1. Auth (JWT + parola hash) ve `market_id`'nin kimlikten türetilmesi (§2.1, §2.2)
2. Rol bazlı yetkilendirme (§2.3)
3. CORS sıkılaştırma + `DEBUG=false` + güvenlik header'ları (§2.4, §2.5)
4. Yıkıcı aksiyonlara onay diyaloğu (§3.4)
5. Sessiz mock fallback'in kaldırılması (§4.2)

### Aşama B — Altyapı ve sağlamlık
6. Dockerfile + docker-compose + CI (test dahil) (§3.1)
7. Rate limiting + girdi sınırları (§2.6)
8. Global exception handler + yapılandırılmış log + audit log (§3.2)
9. Cross-tenant izolasyon testleri, frontend unit testleri (§3.1)

### Aşama C — Ürünü vaadine kavuşturma
10. PDF/PNG render + önizleme/onay akışı (Phase 16)
11. Dosya yükleme + S3/obje depolama
12. Telegram entegrasyonu (webhook + BotConnection)
13. Eksik sayfalar: Markets, Files, Reports, gerçek Dashboard, Settings kalıcılığı

### Aşama D — Ölçek ve cila
14. i18n altyapısı, react-router, react-query
15. Responsive/erişilebilirlik iyileştirmeleri
16. Doküman senkronizasyonu (faz numaraları, API_INTEGRATION örnekleri)

---

*Bu rapor; backend güvenlik/mimari taraması, frontend kullanılabilirlik taraması ve dokümantasyon/altyapı incelemesinin birleştirilmiş çıktısıdır. Dosya:satır referansları 4 Temmuz 2026 tarihli çalışma ağacına aittir.*
