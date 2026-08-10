# Phase 29 Production Smoke Test

Deterministic post-deploy smoke test for the combined Phase 28A + Phase 28B +
Phase 29 production deploy. Run this after every deploy that touches the
Telegram workflow, image resolution, or rendering/quality-gate pipeline.

This document does not deploy anything. It only verifies a deploy that already
happened, per the [Production Deployment](PRODUCTION_DEPLOYMENT.md) "Update
Flow" section (step 9 there points here for Telegram-specific coverage).

Do not run this against a market with real, live customer campaigns unless
you accept it creating a real test campaign in that market. Prefer a
dedicated internal test market and Telegram account.

## 0. Pre-conditions

- Deploy completed: `alembic upgrade head` succeeded, backend/frontend
  containers are up.
- `python -m scripts.bootstrap_production_templates` has run at least once
  (published global supermarket presets exist).
- A Telegram account is linked to a test user with `market_staff` or
  `market_admin` role on the test market
  (`scripts/link_telegram_account.py`).

## 1. Health and readiness

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/db').read().decode())"
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/readiness').read().decode())"
```

Expected: all three return HTTP 200 with `"status": "ok"`. If
`/api/health/readiness` returns 503, read the `checks` object in the response
body to find which dependency (database, storage, telegram_config,
supermarket_templates) is failing, and stop — do not proceed to step 2 until
it is fixed.

Also confirm the frontend is reachable at `https://${APP_DOMAIN}` and returns
200.

## 2. Chromium and render round trip

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -m scripts.readiness_check
```

Expected: JSON report with `"status": "ok"`, including `chromium.ok == true`
and `render.ok == true` (an actual PDF + PNG were rendered and validated).
This is slower than step 1 and deliberately not part of the hot health-check
endpoint — see `backend/app/api/routes/health.py`.

## 3. Telegram flow: basic creation (Scenario 1)

In the linked Telegram account, send:

```
Coca Cola 1L - 29,90
Eti Burçak - 44,90
Sütaş Yoğurt - 74,90
```

Expected in Telegram:

- "Listenizi aldim. Brosur hazirlaniyor..." then the finished flyer PNG within
  a reasonable time (no PDF yet at this step — PDF/PNG confirmation happens
  after `export:confirm`).
- If any of the three products has no safe catalog image, a single concise
  warning naming that product, e.g. "Guvenilir gorsel bulunamadi: Sütaş
  Yoğurt. LP yedegi kullanildi; katalogdan gorsel yukleyebilirsiniz." — the
  flyer must still be produced, not blocked.
- No Python stack trace or internal error text anywhere in the chat.

## 4. Telegram flow: hero edit (Scenario 2)

Send:

```
Coca Cola'yı öne çıkar
```

Expected: acknowledgement naming Coca Cola, an updated flyer with Coca Cola
visually dominant, and the *same three products at the same three prices*.

## 5. Telegram flow: simplify edit (Scenario 3)

Send:

```
Daha sade yap
```

Expected: acknowledgement ("Tasarim sadelestirildi."), a visually simpler
flyer, hero product identity unchanged, and — again — the same three products
at the same three prices as step 3.

## 6. Unresolved image handling (Scenario 4)

If step 3 did not already surface an unresolved-image warning naturally
(e.g. the test market's catalog already had images for all three products),
force it: send a new product list containing one intentionally unmatchable
name, for example:

```
Zzz Nonexistent Test Product 9182 - 5,00
```

Expected: the flyer still renders (LP fallback image for that line), the
warning names that product specifically, and no unrelated product's image is
substituted for it.

## 7. Confirm and duplicate-delivery check

Tap "Generate PDF + PNG" (`export:confirm`). Expected: one PDF and one PNG
delivered. Tap it again (or resend the same Telegram update — e.g. by
retrying the tap quickly twice). Expected: "Bu akis zaten tamamlandi; dosyalar
tekrar gonderilmeyecek." and no second PDF/PNG delivered.

## 8. Record verification

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec backend \
  python -c "
import asyncio
from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models import Campaign, CampaignItem, ExportJob

async def main():
    async with AsyncSessionLocal() as session:
        campaign = (await session.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(1))).first()
        items = (await session.scalars(select(CampaignItem).where(CampaignItem.campaign_id == campaign.id))).all()
        exports = await session.scalar(select(func.count()).select_from(ExportJob).where(ExportJob.campaign_id == campaign.id, ExportJob.status == 'completed'))
        print('campaign_id', campaign.id, 'channel', campaign.channel, 'item_count', len(items))
        print([(i.incoming_name, str(i.price), i.is_hero, i.match_status) for i in items])
        print('completed_export_jobs', exports)

asyncio.run(main())
"
```

Expected:

- Exactly one campaign was created by this smoke test (`channel == "telegram"`).
- Exactly one `CampaignItem` per distinct product sent (3, or 4 if step 6 ran
  as a separate campaign).
- Prices match exactly what was typed (`29.90`, `44.90`, `74.90`).
- Exactly one `is_hero == True` item, matching the Coca Cola edit.
- `completed_export_jobs` reflects one completed final export per confirm
  tap, not two, confirming step 7's duplicate-delivery guard held at the
  database level too.

## 9. Confirm no backend/Telegram errors

```bash
docker compose --env-file .env.production -f docker-compose.production.yml logs --since 30m backend | grep -i "telegram update failed\|ERROR"
```

Expected: no output correlated with the smoke test's `update_id`s /
`campaign_id` from step 8. Any hit here is a blocker — do not consider the
deploy verified.

## 10. Cleanup

Cancel/delete the smoke-test campaign(s) from the test market so they do not
appear in real reporting. Do not delete the exported files from storage
manually; let normal retention handle them.
