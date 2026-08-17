# Stripe Billing — Sandbox Integration

*Durum: Sandbox/TEST modunda tamamlandı. Canlı moda geçiş ayrı, kontrollü bir iş — bkz. "Production'a geçiş" altta.*

Stripe, ödeme/abonelik durumunun tek otoritesidir; LeafletPilot plan hakları (`PLAN_REGISTRY`, `backend/app/services/plans.py`) için tek otorite olmaya devam eder. `Market.subscription_plan` ve `MarketSubscription` satırı **yalnızca** webhook işleme (`app/services/billing/webhook.py`) veya Platform Admin resync (`POST /platform/markets/{id}/billing/resync`) tarafından yazılır — hiçbir mutation endpoint'i (`/billing/checkout`, `/billing/change-plan`, `/billing/cancel`, `/billing/resume`) bu alanları doğrudan yazmaz.

## Ortam değişkenleri

`backend/.env.example` / `.env.production.example` içinde isim olarak mevcut, değer içermez:

- `STRIPE_ENABLED` — false varsayılan; entegrasyon kapalıyken tüm billing endpoint'leri 404/503 döner.
- `STRIPE_SECRET_KEY` — sandbox'ta `rk_test_`/`sk_test_` ile başlamalı; `ENVIRONMENT=production` dışında `sk_live_`/`rk_live_` reddedilir (`app/core/config.py:_validate_enabled_stripe_settings`).
- `STRIPE_WEBHOOK_SECRET` — ≥32 karakter, placeholder olmayan bir değer.
- `STRIPE_PRICE_LOOKUP_KEY_STARTER` / `_STANDARD` / `_PRO` — varsayılanlar zaten oluşturulmuş sandbox Price'ların lookup key'leri: `leafletpilot_starter_monthly_eur`, `leafletpilot_standard_monthly_eur`, `leafletpilot_pro_monthly_eur`.
- `STRIPE_CHECKOUT_SUCCESS_URL` / `STRIPE_CHECKOUT_CANCEL_URL` / `STRIPE_PORTAL_RETURN_URL` — boş bırakılırsa `FRONTEND_BASE_URL` + `/#/settings/billing[...]` türetilir. **Frontend hash router kullanır** (sunucu tarafı route yok) — bu değerler elle set edilirse mutlaka `/#/` segmentini içermeli; aksi halde Stripe kullanıcıyı ödeme sonrası herkese açık ana sayfaya döndürür, kimliği doğrulanmış Billing sayfasına değil. Production'da bu üç URL de HTTPS zorunludur (`_validate_enabled_stripe_settings`).
- `STRIPE_AUTOMATIC_TAX_ENABLED` — false varsayılan; Checkout her zaman `automatic_tax={"enabled": <bu değer>}`'i **açıkça** gönderir (Stripe hesap seviyesi varsayılanlara güvenilmez — bkz. Managed Payments notu altta). VAT/TVA toplanmadığı sürece false kalmalı; ileride VAT devreye alınırsa yalnızca bu flag değişir, kod değişikliği gerekmez.

## Managed Payments — açıkça kapalı

Stripe TEST hesapları, Dashboard'da "Get started" kurulumu tamamlanmamış olsa bile Managed Payments'ı Checkout Session'lar için **varsayılan olarak açık** tutabilir. Managed Payments açıkken Stripe API `automatic_tax[enabled]=true` zorunlu kılar ve vergi/toplam davranışını LeafletPilot'un beklediğinden farklı şekilde değiştirir. Bu yüzden her Checkout Session isteği açıkça `managed_payments={"enabled": false}` gönderir (`app/services/billing/service.py::create_checkout_session`) — hesap seviyesi varsayılana asla güvenilmez.

## Stripe Dashboard (TEST mode) kurulumu

1. Products/Prices: `starter` (5900), `standard` (11900), `pro` (19900) — 3 aylık EUR recurring Price, yukarıdaki lookup key'lerle. (Bu PR öncesinde ayrıca doğrulanmış ve oluşturulmuştur.)
2. Webhook endpoint: `POST {API_BASE}/billing/stripe/webhook` (production: `https://api.leafletpilot.com/api/billing/stripe/webhook`). Abone olunacak event türleri (`app/services/billing/webhook.py` ile birebir):
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `customer.subscription.pending_update_applied`
   - `customer.subscription.pending_update_expired`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `invoice.payment_action_required`

   Signing secret → `STRIPE_WEBHOOK_SECRET`. Kodda desteklenmeyen fazladan event türü eklemeyin.
3. Customer Portal configuration: uygulama ilk portal isteğinde kendi Configuration'ını API üzerinden oluşturur (`metadata.application=leafletpilot` ile işaretli, tekrar kullanılır) — **plan değiştirme ve iptal özellikleri kapalı**, yalnızca ödeme yöntemi güncelleme + fatura geçmişi + fatura adresi açık. Dashboard'da manuel bir Configuration oluşturursanız aynı feature flag'lerini uygulayın; aksi halde Portal, uygulamanın kendi planlı-düşürme/iptal mantığıyla çelişebilir.
4. Restricted API key — minimum izinler, koddaki gerçek Stripe çağrılarından türetilmiştir (bkz. `app/services/billing/service.py`, `webhook.py`):
   - **Prices**: Read (`Price.list`/`Price.retrieve` — plan↔price eşleme)
   - **Checkout Sessions**: Write (`checkout.Session.create`)
   - **Subscriptions**: Write (`Subscription.retrieve`/`Subscription.modify` — Write izni Read'i kapsar)
   - **Subscription Schedules**: Write (`SubscriptionSchedule.create`/`.modify`/`.release`/`.retrieve` — düşürme akışı)
   - **Customer Portal**: Write (`billing_portal.Configuration.list`/`.create`, `billing_portal.Session.create`)
   - **Invoices**: Read (`Invoice.list` — fatura geçmişi) yeterliydi; yükseltme önizlemesi artık `Invoice.create_preview` da çağırıyor (`POST /v1/invoices/create_preview`) — Stripe bu uç noktayı POST olarak sınıflandırdığından restricted key'de muhtemelen **Write** gerektirir, sandbox'ta doğrulanana kadar Write olarak ayarlayın.
   - **Webhooks**: gerekmez — imza doğrulama (`stripe.Webhook.construct_event`) yerel işlemdir, API çağrısı yapmaz.
   - Ayrı bir **Customers** izni gerekmez: uygulama hiçbir zaman `stripe.Customer.*` çağırmaz — Checkout Sessions izni, Checkout'un kendi müşteri oluşturmasına yeter; müşteri sonrasında yalnızca id ile referans alınır.
   - Prod E2E'de gözlemlenen `more_permissions_required` hatası, restricted key'de **Checkout Sessions Write** eksikliğinden kaynaklanıyordu — yukarıdaki liste eksiksiz haliyle doğrulanmıştır.
   - **"Ödeme yöntemini yönet" 502'si (gözlemlenen, henüz üretimde açık)**: `POST /billing/portal`, restricted key'de **Customer Portal: Write** izni eksikse Stripe `PermissionError`/`AuthenticationError` döner; `create_portal_session` bunu artık ayrı yakalayıp "...API anahtarına yeterli izin tanımlı değil..." şeklinde güvenli, Türkçe bir `BillingError` (502) olarak çeviriyor (bkz. `app/services/billing/service.py::create_portal_session`) — önceden bu genel `_stripe_error_to_http` yoluna düşüyordu, aynı 502 ama daha az spesifik bir mesajla. **Kod tarafında yapılacak başka bir şey yok**; kalıcı çözüm restricted key'e Dashboard'dan Customer Portal Write izninin eklenmesidir.

## Abonelik durum politikası

`app/services/billing/service.py` — Stripe `subscription.status` değerleri doğrudan `MarketSubscription.status`'a yansıtılır:

- `active` / `trialing` → tam hak: `market.subscription_plan = plan_code`.
- `past_due` / `incomplete` / `paused` → **grace**: plan değiştirilmez, yalnızca durum güncellenir, müşteri arayüzünde uyarı gösterilir.
- `unpaid` / `canceled` / `incomplete_expired` → `market.subscription_plan = "unassigned"` (geri alınabilir: sonraki başarılı `active` event'i planı geri yükler).

## Yükseltme / Düşürme / İptal

- **Yükseltme**: `Subscription.modify_async(proration_behavior="always_invoice", payment_behavior="pending_if_incomplete")`. Ödeme senkron tamamlanmazsa Stripe `pending_update` döner; hak **verilmez** — yalnızca `customer.subscription.pending_update_applied` event'i planı etkinleştirir. `pending_update_expired` bekleyen değişikliği sessizce temizler.
- **Düşürme**: Subscription Schedule (`SubscriptionSchedule.create_async(from_subscription=...)`, iki faz: mevcut fiyat dönem sonuna kadar, yeni (düşük) fiyat açık uçlu). Fiyat/hak, faz geçişi gerçekleşene kadar **değişmez**; `pending_plan_code`/`pending_change_at`/`pending_change_reason="downgrade"` müşteriye gösterilir.
- **İptal**: `cancel_at_period_end=true` — erişim dönem sonuna kadar sürer, gerçek düşürme `customer.subscription.deleted` event'inde uygulanır. Bekleyen bir düşürme varsa önce schedule serbest bırakılır (`SubscriptionSchedule.release_async`).

## Plan değişikliği önizlemesi (`POST /billing/change-plan-preview`)

`change_plan` çağrılmadan önce frontend her zaman bu salt-okunur uç noktayı çağırır (`Billing.jsx::openPlanChangeModal`) ve sonucu bir onay modalinde (`PlanChangeModal`) gösterir — anlık plan değişikliği yoktur. Hiçbir Stripe/DB state'i mutasyona uğramaz.

- **Yükseltme**: `stripe.Invoice.create_preview_async(subscription=..., subscription_details={items, proration_behavior="always_invoice", proration_date=now})` — `change_plan`'ın gerçek mutasyonuyla **birebir aynı** `proration_behavior`. Bugün tahsil edilecek tutar (`immediate_amount_due`/`net_immediate_amount`), kredi/ücret satırları (`immediate_credit_amount`/`immediate_charge_amount`/`line_items`) doğrudan Stripe'ın önizleme faturasından okunur — manuel oran hesabı **yok**. `next_renewal_amount`/`next_renewal_date`, hedef Price'ın `unit_amount`'ı ve senkronize `current_period_end`'den (ikisi de Stripe-otoriter) türetilir; upgrade'in kendisi anchor'ı değiştirmediği için bu güvenlidir. `is_estimate=true`: onay anındaki gerçek tahsilat (ödeme yöntemi/SCA'ya bağlı) birkaç saniyelik farkla önizlemeden az miktarda sapabilir.
- **Düşürme**: Stripe fatura önizlemesi **hiç çağrılmaz** — `change_plan` düşürmede zaten proration uygulamıyor (bkz. üstte), bu yüzden önizlenecek bir oran hesabı yok. Yanıt tamamen deterministiktir: `immediate_amount_due=0`, `next_renewal_amount`=hedef Price'ın `unit_amount`'ı, `next_renewal_date`=mevcut `current_period_end` (schedule'ın ikinci fazının devreye gireceği tarih). `is_estimate=false`.
- Zaten bir `SubscriptionSchedule`'ı olan abonelikler için (`had_pending_schedule=true`) açıklama metni, bu işlemin bekleyen değişikliğin yerine geçeceğini belirtir — `change_plan` da aynı şeyi yapar (schedule'ı serbest bırakıp yeni değişikliği uygular).

## Webhook güvenilirlik

- **Idempotency**: `stripe_webhook_events.stripe_event_id` DB UNIQUE constraint; aynı event'in eşzamanlı/tekrar teslimleri güvenle no-op (`_claim_event_row`, `SELECT ... FOR UPDATE`) — tam olarak bir aktif işleyici garantisi.
- **Sıra dışı event koruması**: ayrı sıralama imleçleri kullanılır — `MarketSubscription.last_subscription_event_at` (abonelik durum event'leri) ve `MarketSubscription.last_invoice_event_at` (fatura/ödeme event'leri) birbirinden bağımsızdır, biri diğerini asla geride bırakmaz/bastırmaz. Bir imleçten eski bir event durumu geri almaz (`ignored_stale`).
- **Stripe SDK uyumluluğu**: Kurulu Stripe Python SDK'sının `StripeObject`'i `dict` değildir ve `.get()` desteklemez (yalnızca attribute/item erişimi). Webhook yolu ve `sync_subscription_from_stripe_object`/`apply_checkout_completed`/`apply_invoice_event` bu yüzden `_field(obj, key, default)` yardımcı fonksiyonunu kullanır — hem gerçek SDK nesneleri hem birim testi dict fixture'ları için çalışır. Bu uyumsuzluk daha önce her webhook teslimatında `AttributeError` → 500'e yol açıyordu (bkz. altta kurtarma).
- **Kalıcı hatalar** (eşlenmeyen Price, bulunamayan market): event `failed` olarak işaretlenir (terminal), hata **hem** `stripe_webhook_events.error` **hem** `market_subscriptions.sync_error` alanına yazılır (Platform Admin market listesi/detayında görünür), Stripe'a 200 dönülür (retry fırtınası önlenir). Platform Admin resync, hatayı yalnızca başarılı bir otoriter senkronizasyondan sonra temizler.
- **Geçici hatalar kurtarılabilir**: Kalıcı olmayan bir hata (Stripe API blip, DB hatası, veya düzeltilmeden önceki `.get()` hatası gibi bir kod hatası) event satırını terminal olmayan `received` durumunda bırakır — sonraki bir Stripe retry teslimatı satırı yeniden talep edip işleyebilir. Yalnızca `processed` / `ignored` / `ignored_stale` / `failed` terminaldir.

## Webhook kurtarma / yeniden gönderme prosedürü

Bir event `failed` (kalıcı) durumuna düşerse ve kök neden bir kod hatasıysa (örn. bu PR'ın düzelttiği SDK uyumsuzluğu):

1. Kod düzeltmesini deploy et.
2. Stripe Dashboard → Developers → Webhooks → ilgili endpoint → Event'i bul → **Resend**. Bu, aynı `stripe_event_id` ile yeni bir teslimat tetikler.
3. `_claim_event_row`, satırın `failed` (terminal) olduğunu görüp no-op döner — **`failed` olarak işaretlenmiş bir event otomatik olarak yeniden denenmez**, açıkça resend edilmelidir.
4. Alternatif: Platform Admin resync (`POST /platform/markets/{id}/billing/resync`) etkilenen market için Stripe'tan doğrudan otoriter durumu çeker; bu, `stripe_webhook_events` satırının durumunu değiştirmez ama `market_subscriptions.sync_error`'ı başarılı senkronizasyon sonrası temizler.
5. Terminal olmayan (`received`) bir event için ekstra işlem gerekmez — sıradaki Stripe retry teslimatı otomatik olarak yeniden işler.

## Testler

`cd backend && pytest tests/test_billing.py` — plan mapping, checkout RBAC, checkout body içeriği (customer_creation gönderilmez, managed_payments/automatic_tax açık gönderilir, email fallback sırası), durum bazlı hak politikası, sıra dışı event koruması, idempotency, pending-update ödeme güvenliği, sync-error görünürlüğü/resync, pending plan görünürlüğü (müşteri + Platform Admin), gerçek Stripe SDK nesnesi gibi davranan (`.get()` desteklemeyen) fixture'larla webhook/sync uyumluluğu. Gerçek Stripe ağ çağrısı yapılmaz (SDK çağrıları `monkeypatch` ile stub'lanır).

## Manuel E2E

Bu entegrasyon HTTPS webhook endpoint'i gerektirdiğinden (`api.leafletpilot.com`), **production'a karşı manuel E2E için Stripe CLI/`stripe listen` gerekmez** — Stripe Dashboard'daki gerçek webhook endpoint'i kullanılır. Yerel geliştirmede HTTPS tünel yoksa `stripe listen --forward-to localhost:8000/api/billing/stripe/webhook` hâlâ kullanılabilir.

1. Panelden `Başlangıç` seç → Checkout → test kartı `4242 4242 4242 4242` ile tamamla.
2. Stripe, `STRIPE_CHECKOUT_SUCCESS_URL` çözümlenmiş haliyle (`.../#/settings/billing?checkout=success`) kimliği doğrulanmış Billing sayfasına geri döndürmeli — herkese açık ana sayfaya değil.
3. Webhook sonrası panelde plan/durum güncellenmesini doğrula (`checkout.session.completed` + `customer.subscription.created`).
4. `Plus`'a yükselt (senkron veya `stripe trigger`/gerçek SCA kartıyla pending senaryosu) → hakkın yalnızca onay sonrası verildiğini doğrula.
5. `Başlangıç`'a düşür → hakkın dönem sonuna kadar değişmediğini, dönem sonu geçişinde (`customer.subscription.updated`) planın gerçekten değiştiğini doğrula.
6. İptal et → `cancel_at_period_end` → `customer.subscription.deleted` ile erişimin kalktığını doğrula.
7. Backend loglarını kontrol et: `POST /api/billing/stripe/webhook` için tekrarlayan 500 olmamalı (bu PR'ın kapattığı `.get()`/`AttributeError` regresyonu).

**Not**: Ödeme → webhook → yerel abonelik → fatura → Billing UI durumu zincirinin uçtan uca gerçek bir Stripe TEST ödemesiyle doğrulanması, bu PR'ın "tamamlandı" sayılabilmesi için ayrı bir manuel adım olarak kalır — bkz. PR açıklaması.

## Production'a geçiş (bu PR'ın kapsamı dışında)

Ayrı, kontrollü bir görev olarak: `STRIPE_ENABLED=true` + `sk_live_`/`rk_live_` anahtarı yalnızca `ENVIRONMENT=production`'da; canlı Product/Price/webhook Stripe Dashboard'da yeniden oluşturulmalı (sandbox nesneleri canlıya taşınmaz); `STRIPE_CHECKOUT_SUCCESS_URL`/`_CANCEL_URL`/`STRIPE_PORTAL_RETURN_URL` HTTPS zorunlu (`_validate_enabled_stripe_settings`). Faz C (auth/tenancy) canlıya çıkmadan bu adım atılmamalı.
