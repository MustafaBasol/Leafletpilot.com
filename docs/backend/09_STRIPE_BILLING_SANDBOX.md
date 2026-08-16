# Stripe Billing — Sandbox Integration

*Durum: Sandbox/TEST modunda tamamlandı. Canlı moda geçiş ayrı, kontrollü bir iş — bkz. "Production'a geçiş" altta.*

Stripe, ödeme/abonelik durumunun tek otoritesidir; LeafletPilot plan hakları (`PLAN_REGISTRY`, `backend/app/services/plans.py`) için tek otorite olmaya devam eder. `Market.subscription_plan` ve `MarketSubscription` satırı **yalnızca** webhook işleme (`app/services/billing/webhook.py`) veya Platform Admin resync (`POST /platform/markets/{id}/billing/resync`) tarafından yazılır — hiçbir mutation endpoint'i (`/billing/checkout`, `/billing/change-plan`, `/billing/cancel`, `/billing/resume`) bu alanları doğrudan yazmaz.

## Ortam değişkenleri

`backend/.env.example` / `.env.production.example` içinde isim olarak mevcut, değer içermez:

- `STRIPE_ENABLED` — false varsayılan; entegrasyon kapalıyken tüm billing endpoint'leri 404/503 döner.
- `STRIPE_SECRET_KEY` — sandbox'ta `rk_test_`/`sk_test_` ile başlamalı; `ENVIRONMENT=production` dışında `sk_live_`/`rk_live_` reddedilir (`app/core/config.py:_validate_enabled_stripe_settings`).
- `STRIPE_WEBHOOK_SECRET` — ≥32 karakter, placeholder olmayan bir değer.
- `STRIPE_PRICE_LOOKUP_KEY_STARTER` / `_STANDARD` / `_PRO` — varsayılanlar zaten oluşturulmuş sandbox Price'ların lookup key'leri: `leafletpilot_starter_monthly_eur`, `leafletpilot_standard_monthly_eur`, `leafletpilot_pro_monthly_eur`.
- `STRIPE_CHECKOUT_SUCCESS_URL` / `STRIPE_CHECKOUT_CANCEL_URL` / `STRIPE_PORTAL_RETURN_URL` — boş bırakılırsa `FRONTEND_BASE_URL` + `/#/settings/billing` türetilir.

## Stripe Dashboard (TEST mode) kurulumu

1. Products/Prices: `starter` (5900), `standard` (11900), `pro` (19900) — 3 aylık EUR recurring Price, yukarıdaki lookup key'lerle. (Bu PR öncesinde ayrıca doğrulanmış ve oluşturulmuştur.)
2. Webhook endpoint: `POST {API_BASE}/billing/stripe/webhook`, event türleri: `checkout.session.completed`, `customer.subscription.created/updated/deleted`, `customer.subscription.pending_update_applied/expired`, `invoice.paid`, `invoice.payment_failed`, `invoice.payment_action_required`. Signing secret → `STRIPE_WEBHOOK_SECRET`.
3. Customer Portal configuration: uygulama ilk portal isteğinde kendi Configuration'ını API üzerinden oluşturur (`metadata.application=leafletpilot` ile işaretli, tekrar kullanılır) — **plan değiştirme ve iptal özellikleri kapalı**, yalnızca ödeme yöntemi güncelleme + fatura geçmişi + fatura adresi açık. Dashboard'da manuel bir Configuration oluşturursanız aynı feature flag'lerini uygulayın; aksi halde Portal, uygulamanın kendi planlı-düşürme/iptal mantığıyla çelişebilir.

## Abonelik durum politikası

`app/services/billing/service.py` — Stripe `subscription.status` değerleri doğrudan `MarketSubscription.status`'a yansıtılır:

- `active` / `trialing` → tam hak: `market.subscription_plan = plan_code`.
- `past_due` / `incomplete` / `paused` → **grace**: plan değiştirilmez, yalnızca durum güncellenir, müşteri arayüzünde uyarı gösterilir.
- `unpaid` / `canceled` / `incomplete_expired` → `market.subscription_plan = "unassigned"` (geri alınabilir: sonraki başarılı `active` event'i planı geri yükler).

## Yükseltme / Düşürme / İptal

- **Yükseltme**: `Subscription.modify_async(proration_behavior="always_invoice", payment_behavior="pending_if_incomplete")`. Ödeme senkron tamamlanmazsa Stripe `pending_update` döner; hak **verilmez** — yalnızca `customer.subscription.pending_update_applied` event'i planı etkinleştirir. `pending_update_expired` bekleyen değişikliği sessizce temizler.
- **Düşürme**: Subscription Schedule (`SubscriptionSchedule.create_async(from_subscription=...)`, iki faz: mevcut fiyat dönem sonuna kadar, yeni (düşük) fiyat açık uçlu). Fiyat/hak, faz geçişi gerçekleşene kadar **değişmez**; `pending_plan_code`/`pending_change_at`/`pending_change_reason="downgrade"` müşteriye gösterilir.
- **İptal**: `cancel_at_period_end=true` — erişim dönem sonuna kadar sürer, gerçek düşürme `customer.subscription.deleted` event'inde uygulanır. Bekleyen bir düşürme varsa önce schedule serbest bırakılır (`SubscriptionSchedule.release_async`).

## Webhook güvenilirlik

- **Idempotency**: `stripe_webhook_events.stripe_event_id` DB UNIQUE constraint; aynı event'in eşzamanlı/tekrar teslimleri güvenle no-op.
- **Sıra dışı event koruması**: her `MarketSubscription.last_stripe_event_at`'ten eski bir event durumu asla geri almaz (`ignored_stale`).
- **Kalıcı hatalar** (eşlenmeyen Price, bulunamayan market): event `failed` olarak işaretlenir, hata **hem** `stripe_webhook_events.error` **hem** `market_subscriptions.sync_error` alanına yazılır (Platform Admin market listesi/detayında görünür), Stripe'a 200 dönülür (retry fırtınası önlenir). Platform Admin resync, hatayı yalnızca başarılı bir otoriter senkronizasyondan sonra temizler.

## Testler

`cd backend && pytest tests/test_billing.py` — plan mapping, checkout RBAC, durum bazlı hak politikası, sıra dışı event koruması, idempotency, pending-update ödeme güvenliği, sync-error görünürlüğü/resync, pending plan görünürlüğü (müşteri + Platform Admin). Gerçek Stripe ağ çağrısı yapılmaz (SDK çağrıları `monkeypatch` ile stub'lanır).

## Manuel sandbox E2E (otomasyon dışı — Stripe CLI ile)

1. `stripe listen --forward-to localhost:8000/api/billing/stripe/webhook`
2. Panelden `Başlangıç` seç → Checkout → test kartı `4242 4242 4242 4242` ile tamamla.
3. Webhook sonrası panelde plan/durum güncellenmesini doğrula.
4. `Standart`'a yükselt (senkron veya `stripe trigger` ile pending/SCA senaryosu) → hakkın yalnızca onay sonrası verildiğini doğrula.
5. `Başlangıç`'a düşür → hakkın dönem sonuna kadar değişmediğini, `stripe trigger customer.subscription.updated` ile dönem sonu simülasyonunda geçişin gerçekleştiğini doğrula.
6. İptal et → `cancel_at_period_end` → `stripe trigger customer.subscription.deleted` ile erişimin kalktığını doğrula.

## Production'a geçiş (bu PR'ın kapsamı dışında)

Ayrı, kontrollü bir görev olarak: `STRIPE_ENABLED=true` + `sk_live_`/`rk_live_` anahtarı yalnızca `ENVIRONMENT=production`'da; canlı Product/Price/webhook Stripe Dashboard'da yeniden oluşturulmalı (sandbox nesneleri canlıya taşınmaz); `STRIPE_CHECKOUT_SUCCESS_URL`/`_CANCEL_URL`/`STRIPE_PORTAL_RETURN_URL` HTTPS zorunlu (`_validate_enabled_stripe_settings`). Faz C (auth/tenancy) canlıya çıkmadan bu adım atılmamalı.
