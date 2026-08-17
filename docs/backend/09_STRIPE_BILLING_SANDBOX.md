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

**`unassigned` canonical DB değeri (migration `20260817_0026`)**: `market.subscription_plan = "unassigned"` uygulama katmanında (`_apply_entitlement`, `plans.py::PLAN_REGISTRY`, `entitlements.py`) her zaman geçerli bir durumdu, ancak `markets` tablosundaki `ck_markets_subscription_plan` CHECK constraint'i bunu hiç allow-list'e almamıştı. Production'da gerçek bir `customer.subscription.deleted` event'i bu satırı yazmaya çalışınca `CheckViolationError`/`IntegrityError` fırlattı ve webhook `stripe_webhook_events` tablosunda kalıcı olarak `status="received"` durumunda takılı kaldı (terminal olmayan, ama işlenmemiş). Constraint artık `starter | standard | growth | pro | unassigned` kümesini kabul ediyor — bkz. `backend/alembic/versions/20260817_0026_market_subscription_plan_unassigned.py` ve `app/models/market.py::MARKET_SUBSCRIPTION_PLAN_CODES` (ORM tarafında da aynı liste `CheckConstraint` olarak ayna tutulur, şema/kod birbirinden sapmasın diye). Bu saf bir şema-katch-up'tır; hiçbir uygulama mantığı değişmedi.

**Terminal iptal + sıra dışı event koruması**: Gerçek bir Stripe iptali (`status=canceled`, `cancel_at_period_end=false`, `canceled_at` dolu) geldiğinde `customer.subscription.deleted` event'i satırı doğrudan bu terminal duruma yazar ve `market.subscription_plan="unassigned"` olur — event kendi otoriter payload'ını taşır, yeniden fetch edilmez (bkz. `SUBSCRIPTION_EVENT_TYPES_REQUIRING_REFETCH`). Bu iptalden SONRA, iptalden ÖNCEki bir zaman damgasıyla (`event.created`) geç gelen bir `customer.subscription.updated` event'i **aboneliği diriltmez** — `last_subscription_event_at` imleci zaten iptal event'inin zaman damgasında olduğu için daha eski event `sync_subscription_from_stripe_object` içinde sessizce `ignored_stale` olarak atılır (regresyon testi: `test_stale_subscription_updated_after_deletion_does_not_resurrect_when_test_database_url_is_configured`, `backend/tests/test_billing.py`).

## Yükseltme / Düşürme / İptal

- **Yükseltme**: `Subscription.modify_async(proration_behavior="always_invoice", payment_behavior="pending_if_incomplete")`. Ödeme senkron tamamlanmazsa Stripe `pending_update` döner; hak **verilmez** — yalnızca `customer.subscription.pending_update_applied` event'i planı etkinleştirir. `pending_update_expired` bekleyen değişikliği sessizce temizler.
- **Düşürme**: Subscription Schedule (`SubscriptionSchedule.create_async(from_subscription=...)`, iki faz: mevcut fiyat dönem sonuna kadar, yeni (düşük) fiyat açık uçlu). Fiyat/hak, faz geçişi gerçekleşene kadar **değişmez**; `pending_plan_code`/`pending_change_at`/`pending_change_reason="downgrade"` müşteriye gösterilir.
- **İptal**: `cancel_at_period_end=true` — erişim dönem sonuna kadar sürer, gerçek düşürme `customer.subscription.deleted` event'inde uygulanır. Bekleyen bir düşürme varsa önce schedule serbest bırakılır (`SubscriptionSchedule.release_async`).

## Terminal abonelik durumu — yeni Checkout zorunluluğu (PR #69 hotfix)

**Production olayı**: Gerçek bir TEST aboneliği iptal edildi (`customer.subscription.deleted` → `MarketSubscription.status="canceled"`, `plan_code="unassigned"`, `Market.subscription_plan="unassigned"` — bkz. yukarıdaki terminal iptal davranışı). Ancak Billing sayfası bu satırı hâlâ değiştirilebilir bir abonelikmiş gibi ele aldı: eski Pro fiyatı/yenileme tarihi güncelmiş gibi gösterildi, "Aboneliği iptal et" görünür kaldı, kullanım kartı `4 / 0` gösterdi, ve bir plan tıklaması `openPlanChangeModal`'ı tetikleyip `POST /billing/change-plan`'a gitti. Backend, satırda hâlâ eski (artık iptal edilmiş) bir `stripe_subscription_id` olduğu için `_require_subscription_row`'u geçti ve `SubscriptionSchedule.create_async`'a kadar ilerledi; Stripe bunu `400 invalid_request_error` ("You cannot migrate a subscription that is currently in the `canceled` status.") ile reddetti ve bu, `_stripe_error_to_http` üzerinden opak bir `502 Bad Gateway` olarak istemciye döndü.

**Lifecycle sınıflandırması** (hem frontend hem backend, tek kaynaktan): backend `CHECKOUT_BLOCKING_STATUSES = {active, trialing, past_due, incomplete, paused}` — bu market'in Stripe'ta hâlâ aktif/devam eden bir aboneliği olduğu anlamına gelir, checkout'u bu yüzden bloklar VE plan değişikliğine izin verir. `DOWNGRADE_TO_UNASSIGNED_STATUSES = {unpaid, canceled, incomplete_expired}` (+ hiç satır olmaması) terminal/yok durumdur: checkout'a izin verir, plan değişikliğini reddeder. Frontend `Billing.jsx::CHANGEABLE_SUBSCRIPTION_STATUSES` bu backend kümesiyle birebir aynıdır (`active/trialing/past_due/incomplete/paused`) — iki katman farklı statü listeleri icat etmez.

- **Backend guard** (`app/services/billing/service.py::_require_changeable_subscription_row`): `change_plan` ve `preview_change_plan`, satırı `CHANGEABLE_SUBSCRIPTION_STATUSES` içinde olmayan (veya hiç var olmayan) bir abonelik için **hiçbir Stripe çağrısından önce** `BillingError("Bu abonelik artık aktif değil. Yeni bir plan başlatmak için ödeme adımını kullanın.", status_code=409)` fırlatır. `SubscriptionSchedule.create_async`/`Invoice.create_preview_async`'a asla ulaşılmaz — bkz. `test_change_plan_rejects_terminal_subscription_before_any_stripe_call_...`, `test_change_plan_preview_rejects_terminal_subscription_before_any_stripe_call_...` (`backend/tests/test_billing.py`).
- **Checkout tarafı zaten korumalıydı**: `create_checkout_session`'daki mevcut overlap-koruması (bkz. PART H testleri: `test_checkout_allowed_after_terminal_subscription_confirmed_terminal_on_stripe_...`) local terminal satırı Stripe'a karşı otoriter olarak doğrular ve eski `stripe_subscription_id`'yi yeniden kullanmadan yeni bir Checkout Session'a izin verir — bu PR bu davranışı değiştirmedi, yalnızca doğruladı.
- **Frontend routing** (`Billing.jsx`): plan kartı tıklaması artık `isActiveSubscription ? openPlanChangeModal(planCode) : handleCheckout(planCode)` — terminal/unassigned için her zaman `POST /billing/checkout`'a gider, `change-plan-preview`/`change-plan`'a asla dokunmaz, `PlanChangeModal` hiç açılmaz.
- **Terminal UI durumu**: "Mevcut Abonelik" kartı `isActiveSubscription=false` iken eski fiyat/dönem bilgisini göstermez — "Aktif abonelik yok. Devam etmek için aşağıdan bir plan seçin." mesajı ve (varsa) `canceled_at` üzerinden açıkça geçmişe ait ("Son aboneliğiniz ... iptal edildi.") bir not gösterir. "Plan / Kullanım" kartı `plan.code === "unassigned"` iken `X / 0` ilerleme çubuğu yerine "Aktif plan yok. Plan seçtiğinizde kullanım limitleri burada görüntülenecek." gösterir. "Aboneliği iptal et"/"Aboneliği devam ettir" aksiyon satırı yalnızca `isActiveSubscription` iken render edilir. Ödeme yöntemi portalı ise (fatura geçmişi/kart yönetimi için) `hasSubscriptionRow` (satır var mı, statüden bağımsız) ile kalmaya devam eder — terminal bir abonelik için de erişilebilir kalır, hiçbir yerde "aktif abonelik" ima etmez.

## Plan değişikliği önizlemesi (`POST /billing/change-plan-preview`)

`change_plan` çağrılmadan önce frontend her zaman bu salt-okunur uç noktayı çağırır (`Billing.jsx::openPlanChangeModal`) ve sonucu bir onay modalinde (`PlanChangeModal`) gösterir — anlık plan değişikliği yoktur. Hiçbir Stripe/DB state'i mutasyona uğramaz.

- **Yükseltme**: `stripe.Invoice.create_preview_async(subscription=..., subscription_details={items, proration_behavior="always_invoice", proration_date=now})` — `change_plan`'ın gerçek mutasyonuyla **birebir aynı** `proration_behavior`. Bugün tahsil edilecek tutar (`immediate_amount_due`/`net_immediate_amount`), kredi/ücret satırları (`immediate_credit_amount`/`immediate_charge_amount`/`line_items`) doğrudan Stripe'ın önizleme faturasından okunur — manuel oran hesabı **yok**. `next_renewal_amount`/`next_renewal_date`, hedef Price'ın `unit_amount`'ı ve senkronize `current_period_end`'den (ikisi de Stripe-otoriter) türetilir; upgrade'in kendisi anchor'ı değiştirmediği için bu güvenlidir. `is_estimate=true`: onay anındaki gerçek tahsilat (ödeme yöntemi/SCA'ya bağlı) birkaç saniyelik farkla önizlemeden az miktarda sapabilir.
- **Düşürme**: Stripe fatura önizlemesi **hiç çağrılmaz** — `change_plan` düşürmede zaten proration uygulamıyor (bkz. üstte), bu yüzden önizlenecek bir oran hesabı yok. Yanıt tamamen deterministiktir: `immediate_amount_due=0`, `next_renewal_amount`=hedef Price'ın `unit_amount`'ı, `next_renewal_date`=mevcut `current_period_end` (schedule'ın ikinci fazının devreye gireceği tarih). `is_estimate=false`.
- Zaten bir `SubscriptionSchedule`'ı olan abonelikler için (`had_pending_schedule=true`) açıklama metni, bu işlemin bekleyen değişikliğin yerine geçeceğini belirtir — `change_plan` da aynı şeyi yapar (schedule'ı serbest bırakıp yeni değişikliği uygular).

## Yükseltme sonrası UI senkronizasyonu (frontend, `src/pages/Billing.jsx`)

`POST /billing/change-plan`'ın `{"status": "applied"}` dönmesi, Stripe mutasyonunun kabul edildiği anlamına gelir — yerel `MarketSubscription` satırı **hâlâ yalnızca** ilgili webhook (`customer.subscription.updated`) işlendiğinde yazılır (bkz. dosyanın en üstündeki çekirdek kural). Webhook, mutasyon yanıtından bir-birkaç saniye sonra ulaşabildiğinden, `confirmPlanChange` mutasyon sonrası hemen `load()`'a güvenmez:

- **`pending_payment`** / **`scheduled` (düşürme)**: plan zaten değişmemiştir (ödeme onayı bekliyor / dönem sonuna ertelenmiş) — modal hemen kapanır, ilgili bilgi mesajı gösterilir, tek bir `load()` yeterlidir. Düşürme hiçbir zaman anlık bir state değişikliği olarak ele alınmaz.
- **`applied` (senkron yükseltme)**: modal "Plan değişikliğiniz işleniyor..." durumuna geçer (buton: "Senkronize ediliyor...", kapatma yine devre dışı) ve **sınırlı** bir yeniden-çekme döngüsü çalışır — `PLAN_SYNC_MAX_ATTEMPTS = 4` deneme, denemeler arası `PLAN_SYNC_RETRY_DELAY_MS = 1500` ms bekleme, her denemede `load()` çağrılıp dönen `subscription.plan_code`'un hedef plana eşit olup olmadığı kontrol edilir. Eşleşirse modal kapanır ve "`<Plan>` planınız etkinleştirildi." mesajı gösterilir. Bu döngü **kesinlikle sürekli polling'e dönüşmez** (`setInterval` yok) ve her zaman sınırlı sayıda denemeden sonra durur.
- Sınırlı deneme tükenip hâlâ senkronize olmadıysa: "Ödemeniz alındı. Plan bilgileriniz birkaç saniye içinde güncellenecek." mesajı ve yanında manuel bir "Yenile" aksiyonu (`handleManualSync`) gösterilir — kullanıcı tam sayfa yenilemeye asla ihtiyaç duymaz.
- Mutasyon isteği hata verirse (`catch` bloğu): modal **kapanmaz**, plan asla değişmiş gibi gösterilmez — hata modalin içinde gösterilir, kullanıcı tekrar deneyebilir veya vazgeçebilir.
- Bu tasarım çekirdek kuralı bozmaz: hiçbir frontend kodu `subscription.plan_code`'u Stripe mutasyon yanıtından tahmin ederek set etmez; tek otoriteli kaynak her zaman `load()`'un döndürdüğü, backend'in webhook/resync ile yazdığı gerçek durumdur.

## Webhook güvenilirlik

- **Idempotency**: `stripe_webhook_events.stripe_event_id` DB UNIQUE constraint; aynı event'in eşzamanlı/tekrar teslimleri güvenle no-op (`_claim_event_row`, `SELECT ... FOR UPDATE`) — tam olarak bir aktif işleyici garantisi.
- **Sıra dışı event koruması**: ayrı sıralama imleçleri kullanılır — `MarketSubscription.last_subscription_event_at` (abonelik durum event'leri) ve `MarketSubscription.last_invoice_event_at` (fatura/ödeme event'leri) birbirinden bağımsızdır, biri diğerini asla geride bırakmaz/bastırmaz. Bir imleçten eski bir event durumu geri almaz (`ignored_stale`).
- **Stripe SDK uyumluluğu**: Kurulu Stripe Python SDK'sının `StripeObject`'i `dict` değildir ve `.get()` desteklemez (yalnızca attribute/item erişimi). Webhook yolu ve `sync_subscription_from_stripe_object`/`apply_checkout_completed`/`apply_invoice_event` bu yüzden `_field(obj, key, default)` yardımcı fonksiyonunu kullanır — hem gerçek SDK nesneleri hem birim testi dict fixture'ları için çalışır. Bu uyumsuzluk daha önce her webhook teslimatında `AttributeError` → 500'e yol açıyordu (bkz. altta kurtarma).
- **`invoice.paid` → Subscription id çıkarımı (Stripe SDK `stripe==15.5.0`, API sürümü `2026-07-29.dahlia`)**: Bu API sürümünde `Invoice` nesnesinin artık üst seviye bir `subscription` alanı **yok** — production'da tüm `invoice.paid` (ilk abonelik faturası ve yükseltme/proration faturaları dahil) `"Invoice event has no associated subscription."` ile kalıcı olarak başarısız oluyordu. Gerçek ilişki artık `invoice.parent.subscription_details.subscription` altında (`invoice.parent.type == "subscription_details"`; quote'tan üretilen faturalarda `"quote_details"` ve gerçekten subscription yok). `app/services/billing/service.py::_subscription_id_from_invoice` bu üç yolu sırayla dener ve **tamamı `_field`/`_as_id` üzerinden**, yani `.get()` desteklemeyen gerçek `StripeObject`'lere karşı da çalışır:
  1. `invoice.parent.subscription_details.subscription` (güncel API)
  2. üst seviye `invoice.subscription` (eski API sürümleri / mevcut fixture'lar için legacy fallback)
  3. `invoice.lines.data[0].parent.subscription_item_details.subscription` (satır seviyesi son çare)

  Ekstra Stripe API çağrısı gerekmez (salt veri-şekli okuma) ve ek restricted-key izni gerektirmez.
- **Kalıcı hatalar** (eşlenmeyen Price, bulunamayan market/abonelik): event `failed` olarak işaretlenir, hata **hem** `stripe_webhook_events.error` **hem** `market_subscriptions.sync_error` alanına yazılır (Platform Admin market listesi/detayında görünür), Stripe'a 200 dönülür (retry fırtınası önlenir). Platform Admin resync, hatayı yalnızca başarılı bir otoriter senkronizasyondan sonra temizler.
- **`failed` terminal DEĞİLDİR — yeniden denenebilir** (PR #69 hotfix): `failed` görünüşte kalıcı olsa da (yanlış eşleme, eksik yerel satır...) kök neden düzeldiğinde (kod deploy'u, eksik satırın senkronize olması, ...) aynı event'in yeniden teslimi tekrar işlenmelidir. `TERMINAL_WEBHOOK_STATUSES = {processed, ignored, ignored_stale}` — yalnızca bu üçü no-op'tur; `received` ve `failed` yeniden talep edilebilir (`RETRYABLE_WEBHOOK_STATUSES`). `_claim_event_row`, `failed` bir satırı aynı `SELECT ... FOR UPDATE` kilidiyle yeniden talep eder, eski hatayı temizler ve dispatch'i yeniden çalıştırır — yeni satır eklenmez, eşzamanlılık koruması (tek aktif işleyici) korunur.
- **Geçici hatalar da kurtarılabilir**: Kalıcı olmayan bir hata (Stripe API blip, DB hatası) event satırını `received` durumunda bırakır — davranışı `failed`'dan farksız, ikisi de retryable.

## Webhook kurtarma / yeniden gönderme prosedürü

Bir event `failed` durumuna düşerse:

1. Kök neden bir kod hatasıysa, düzeltmeyi deploy et; kök neden eksik/gecikmiş bir yerel kayıtsa (örn. `invoice.paid` ilgili `customer.subscription.created`'dan önce geldiyse), o kaydın oluşmasını bekle.
2. Stripe Dashboard → Developers → Webhooks → ilgili endpoint → Event'i bul → **Resend**. Bu, aynı `stripe_event_id` ile yeni bir teslimat tetikler.
3. `_claim_event_row`, `failed` satırı yeniden talep eder (terminal değildir) ve dispatch'i baştan çalıştırır — **Stripe Dashboard'da görünen 200 yanıtı, yalnızca yerel `stripe_webhook_events` satırı da `failed`'dan çıkıp `processed`/`ignored`/`ignored_stale`'e geçtiğinde anlamlıdır**; 200, HTTP seviyesinde her zaman dönülür (bkz. yukarı), event'in gerçekten kurtarıldığının kanıtı değildir — DB'den doğrula.
4. Kurtarma başarısız olursa (kök neden hâlâ geçerliyse) satır yine `failed`'a döner, ama artık en güncel/sanitize edilmiş hata mesajıyla; eski hata mesajı korunmaz.
5. Alternatif: Platform Admin resync (`POST /platform/markets/{id}/billing/resync`) etkilenen market için Stripe'tan doğrudan otoriter durumu çeker; bu, `stripe_webhook_events` satırının durumunu değiştirmez ama `market_subscriptions.sync_error`'ı başarılı senkronizasyon sonrası temizler.

**Bu PR'ın kapattığı iki spesifik production olayı için resend sırası**:

1. Deploy sonrası migration `20260817_0026`'nın uygulandığını doğrula (`alembic current` → `20260817_0026`).
2. Stripe Dashboard → Developers → Webhooks → prod endpoint → **`customer.subscription.deleted`** event'ini bul (constraint hatasıyla `failed` olan) → **Resend**. Beklenen sonuç: `MarketSubscription.status="canceled"`, `cancel_at_period_end=false`, `canceled_at` dolu, `Market.subscription_plan="unassigned"`, webhook satırı `processed`.
3. Aynı Dashboard'da **`invoice.paid`** olarak `failed` işaretli event'leri bul (hem ilk abonelik faturası hem yükseltme/proration faturaları) → her birini **Resend** et. Beklenen sonuç: ilgili `MarketSubscription.last_payment_status="paid"`, `latest_invoice_id` güncellenir, webhook satırı `processed`.
4. Her resend sonrası DB'yi doğrula (Dashboard'daki 200 tek başına yeterli kanıt değildir): `SELECT status, processed_at, error FROM stripe_webhook_events WHERE stripe_event_id = '...'` → `status='processed'`, `processed_at` dolu, `error` NULL olmalı.
5. Platform Admin → Faturalandırma panelinde (`/#/platform/billing`) "Webhook Sağlığı" ve "Son Faturalandırma Hataları" bölümlerinden `failed` sayacının düştüğünü doğrula.

## Testler

`cd backend && pytest tests/test_billing.py` — plan mapping, checkout RBAC, checkout body içeriği (customer_creation gönderilmez, managed_payments/automatic_tax açık gönderilir, email fallback sırası), durum bazlı hak politikası, sıra dışı event koruması, idempotency, pending-update ödeme güvenliği, sync-error görünürlüğü/resync, pending plan görünürlüğü (müşteri + Platform Admin), gerçek Stripe SDK nesnesi gibi davranan (`.get()` desteklemeyen) fixture'larla webhook/sync uyumluluğu. Gerçek Stripe ağ çağrısı yapılmaz (SDK çağrıları `monkeypatch` ile stub'lanır).

Bu PR ayrıca ekliyor: `ck_markets_subscription_plan`'ın `unassigned`'ı kabul ettiğini ve geçersiz değerleri hâlâ reddettiğini doğrulayan constraint testleri; gerçek production regresyonunu birebir üreten terminal iptal testi (`test_subscription_deleted_writes_unassigned_plan_without_constraint_violation_...`) ve iptal-sonrası-sıra-dışı-event regresyon testi; modern (`invoice.parent.subscription_details.subscription`), legacy (üst seviye `invoice.subscription`) ve satır-seviyesi fallback şekillerinin tümünü kapsayan `_subscription_id_from_invoice` testleri (`.get()` desteklemeyen `_FakeStripeObject` dahil); ilk abonelik/yükseltme-proration/ilgisiz/yinelenen/sıra-dışı `invoice.paid` senaryoları; `GET /platform/billing/health` için DB-backed aggregation + sır sızdırmama testleri (`backend/tests/test_platform_billing.py`).

**PR #69 hotfix'i ekliyor** (`failed` webhook retry): `failed` bir event'in resend ile yeniden işlenip kurtarılabildiğini kanıtlayan `test_failed_webhook_event_is_retryable_on_resend_...`; `processed`/`ignored`/`ignored_stale`'in hâlâ terminal kaldığını (resend'in dispatch'i tekrar tetiklemediğini) kanıtlayan `test_processed_webhook_event_remains_idempotent_on_resend_...` ve `test_ignored_and_ignored_stale_webhook_events_remain_terminal_on_resend_...`; aynı `failed` event'in eşzamanlı iki resend'inde tek aktif işleyici garantisinin korunduğunu kanıtlayan `test_concurrent_retries_of_failed_webhook_event_serialize_single_active_processor_...`; başarısız bir retry'ın eski hata mesajını değil en güncel hatayı sakladığını kanıtlayan `test_repeated_failed_retry_replaces_the_stale_error_...` (tümü `backend/tests/test_billing.py`).

Frontend: `npm run test:platform` (`src/pages/platform/PlatformBilling.test.mjs`, `src/api/platformApi.test.mjs`) — sağlık kartlarının, TEST/LIVE rozetinin, webhook uyarı tonunun, plan eşleştirme tablosunun ve son hatalar bölümünün var olduğunu, hiçbir Stripe secret alanının kaynak koduna sızmadığını doğrular (bu harness gerçek DOM render'ı değil, kaynak/metin tabanlı assertion kullanır — bkz. `src/components/ui/PlanChangeModal.test.mjs` ile aynı desen).

**PR #69 terminal lifecycle hotfix'i ekliyor**: `change_plan`/`preview_change_plan`'ın `canceled`/`unpaid`/`incomplete_expired`/satır-yok durumlarını hiçbir Stripe çağrısından önce `409` ile reddettiğini kanıtlayan `test_change_plan_rejects_terminal_subscription_before_any_stripe_call_...`, `test_change_plan_preview_rejects_terminal_subscription_before_any_stripe_call_...`, `test_change_plan_rejects_when_no_subscription_row_at_all_...`, `test_change_plan_preview_rejects_when_no_subscription_row_at_all_...` (hepsi `SubscriptionSchedule.create_async`/`Invoice.create_preview_async`/`Subscription.retrieve_async`'ı çağrılırsa `AssertionError` fırlatan stub'larla, Stripe'a hiç dokunulmadığını kanıtlar); HTTP seviyesinde eski `502`'nin artık `409`'a döndüğünü kanıtlayan `test_change_plan_route_rejects_canceled_subscription_with_409_not_502_...` (`backend/tests/test_billing.py`). Frontend: `npm run test:billing-ui` (`src/pages/Billing.checkout.test.mjs`) — `CHANGEABLE_SUBSCRIPTION_STATUSES`'ın backend `CHECKOUT_BLOCKING_STATUSES` ile birebir aynı olduğunu, plan tıklamasının/CTA metninin/iptal-devam-ettir satırının artık `isActiveSubscription`'a bağlı olduğunu (eski genel `hasSubscription` truthy kontrolüne değil), terminal durumda eski fiyat/tarih bilgisinin ve `4 / 0` kullanım çubuğunun render edilmediğini doğrular.

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

## Platform Admin Billing Operations Dashboard

`GET /api/platform/billing/health` (`backend/app/api/routes/platform_billing.py::billing_health`) + `/#/platform/billing` (`src/pages/platform/PlatformBilling.jsx`) — Platform Admin'in tek bakışta "Stripe doğru yapılandırılmış mı, webhook'lar sağlıklı mı, abonelikler senkronize mi, hangi marketler resync gerektiriyor?" sorularına cevap vermesi için. Mevcut "Plan Eşleştirmeleri" tablosu (Price↔plan sağlığı) aynı sayfada, altta korunur.

- **Ortam (TEST/LIVE)**: `service.py::_environment_tag()` ile aynı mantık — `STRIPE_SECRET_KEY`'in `sk_live_`/`rk_live_` ile başlayıp başlamadığına bakar. Stripe secret/webhook key değeri **hiçbir zaman** response'a girmez.
- **Müşteri Portalı hazırlığı (`portal_status`)**: Her sayfa yüklemesinde Stripe'a canlı bir istek **atılmaz** (maliyetli olur) — `service.py::_portal_readiness_status()` yalnızca bu process ömrü boyunca `create_portal_session` gerçekten başarıyla çalışıp `_PORTAL_CONFIGURATION_CACHE`'i doldurmuşsa `"ready"` döner; aksi halde Stripe etkinse `"not_checked"`, değilse `"unavailable"`. Yani `STRIPE_ENABLED=true` olması tek başına asla `"ready"` görünmesine yol açmaz — sahte pozitif yok.
- **Webhook/abonelik/plan sayaçları ve "Dikkat Gerektiren Marketler"**: Tamamı yerel DB agregasyonu (`StripeWebhookEvent`/`MarketSubscription`/`Market` üzerinde `GROUP BY`) — her market için ayrı Stripe API çağrısı **yapılmaz**. "Dikkat Gerektiren Marketler" iki yerel sinyali birleştirir: `MarketSubscription.sync_error is not null` ve marketine bağlı en az bir `failed` webhook event'i olan marketler (üst sınır 20 satır).
- **Sır sızdırmama**: Tüm hata metinleri (`sync_error`, webhook `error`) response'a girmeden önce `_sanitize_error()`'dan geçer — `sk_test_`/`sk_live_`/`rk_test_`/`rk_live_`/`whsec_` önekinden sonraki karakterler `[redacted]` ile değiştirilir (önek okunabilir kalır, hangi tür sırrın sızdığını teşhis için; asıl materyal asla).

## Production'a geçiş (bu PR'ın kapsamı dışında)

Ayrı, kontrollü bir görev olarak: `STRIPE_ENABLED=true` + `sk_live_`/`rk_live_` anahtarı yalnızca `ENVIRONMENT=production`'da; canlı Product/Price/webhook Stripe Dashboard'da yeniden oluşturulmalı (sandbox nesneleri canlıya taşınmaz); `STRIPE_CHECKOUT_SUCCESS_URL`/`_CANCEL_URL`/`STRIPE_PORTAL_RETURN_URL` HTTPS zorunlu (`_validate_enabled_stripe_settings`). Faz C (auth/tenancy) canlıya çıkmadan bu adım atılmamalı.
