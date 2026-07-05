# LeafletPilot — Proje Rehberi

Yerel marketler için haftalık kampanya broşürlerini mesajlaşma uygulaması üzerinden otomatik üreten B2B SaaS. Kuzey yıldızı: **"Market sahibi Telegram'dan listeyi gönderir, 5 dakikada onaylı broşür PDF'i elindedir."**

## Yön Belirleyen Dosyalar (önce bunlara bak)

- `docs/YOL_HARITASI.md` — **sıradaki iş ne?** Tek otorite bu dosya; fazlar sıralıdır, sıra bozulmaz.
- `docs/SATILABILIRLIK_RAPORU.md` — ticari öncelikler ve neyin neden önemli olduğu
- `docs/PROJE_INCELEME_RAPORU.md` — güvenlik açıkları ve teknik borç listesi
- `docs/design/11_MVP_SCOPE.md` — MVP kapsamı, MVP'de OLMAYACAKLAR listesi (kapsam kaymasını engeller)
- `docs/backend/08_IMPLEMENTATION_PHASES.md` — faz geçmişi (her fazdan sonra güncelle)

## Mimari

- **Backend** (`backend/`): FastAPI + SQLAlchemy 2 async + asyncpg + Alembic, PostgreSQL. Katmanlar: `app/api/routes/` (ince router'lar) → `app/services/` (iş mantığı) → `app/models/` + `app/schemas/`. Bu ayrıma sadık kal: route'a iş mantığı yazma.
- **Frontend** (`src/`): React 19 + Vite, kütüphanesiz elle hash-router (`App.jsx`), UI primitifleri `src/components/ui/`. **Tüm veri erişimi `src/data/dataSource.js` üzerinden** — mock/gerçek API geçişini bu katman yapar; sayfalardan doğrudan `src/api/*` çağırma.
- **Landing page**: `src/pages/Landing.jsx` — giriş yapmamış kullanıcının `/`'da gördüğü pazarlama sayfası.
- UI dili **Türkçe**; tasarım token'ları `src/styles.css` başında (`docs/design/02_DESIGN_SYSTEM.md` ile uyumlu).

## Çalıştırma

```bash
# Backend (backend/ içinde, Python >= 3.11)
alembic upgrade head
python scripts/seed_dev_data.py     # demo market + katalog
uvicorn app.main:app --reload       # http://127.0.0.1:8000/api

# Frontend (kök dizinde)
npm run dev
# .env.local: VITE_USE_REAL_API=true ise backend + seed şart; yoksa mock mod
```

Test: `cd backend && pytest` (DB testleri `TEST_DATABASE_URL` ister, yoksa skip). Frontend: `npm run build` + `npm run validate`.

## Kritik Bilinmesi Gerekenler

1. **Auth henüz yok.** Tenancy `X-Market-Id` header placeholder'ı (`backend/app/api/deps.py`). Bu bilinçli bir MVP kararı ama **internete açılmadan önce Faz C (auth) zorunlu** — yeni endpoint yazarken market scoping'i servis katmanında uygulamayı unutma (mevcut servislerdeki deseni takip et).
2. **Render/Telegram/upload placeholder.** `ExportJob` ve `CampaignFile` sadece kayıt; gerçek dosya üretimi Faz A'nın işi.
3. **Yeni özellik eklerken:** `11_MVP_SCOPE.md`'deki "MVP'de Olmayacaklar" listesini kontrol et; oradaysa yapma, `YOL_HARITASI.md` P2'ye not düş.
4. **Mock veri:** `src/data/mockData.js`. Gerçek API moduna yeni alan eklerken `dataSource.js`'teki `map*()` çevirmenlerini ve Türkçe etiket haritalarını güncelle.
5. Migration'lar Alembic ile: model değişince `alembic revision --autogenerate` + elle kontrol; migration dosya adlandırması `YYYYMMDD_NNNN_açıklama`.

## Kod Kuralları

- Commit'lemeden önce: backend değişikliğinde `pytest`, frontend değişikliğinde `npm run build`.
- Route'lar ince, iş mantığı serviste; hata durumları `HTTPException` + mevcut `_not_found`/409 desenleri.
- Frontend'de yeni sayfa: `src/pages/` + `App.jsx` if-merdiveni + `src/routes/routes.js` (nav/pageMeta).
- İşlevsiz (dekoratif) buton/filtre ekleme — çalışmayan UI demo güvenini bozuyor; ya bağla ya koyma.
