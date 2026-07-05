# File Storage And Export Plan

## Phase 17 Status

Phase 16 added deterministic HTML preview rendering for campaigns through
`GET /api/campaigns/{campaignId}/preview-html`. The endpoint renders campaign
items with the selected template config and returns HTML in the API response.

Phase 17 turns that HTML into real local PDF/PNG files through
`POST /api/campaigns/{campaignId}/export-jobs`. The API creates an `ExportJob`,
renders synchronously with Playwright, stores bytes under `LOCAL_STORAGE_DIR`,
creates `CampaignFile` rows, and exposes a guarded download endpoint. The
FastAPI service calls Playwright's sync API from a background thread so Windows
does not launch Chromium from Uvicorn's request event loop. There is still no
S3/R2 provider and no background worker.

Required browser setup after installing backend dependencies:

```powershell
.\.venv\Scripts\python -m playwright install chromium
```

## Storage Provider

Current MVP storage is local filesystem storage. Set:

```text
LOCAL_STORAGE_DIR=storage
```

Relative paths resolve under `backend/`. Generated files are ignored by git.

Future production storage should use S3-compatible object storage so the backend
can run against AWS S3, Cloudflare R2, Supabase Storage, MinIO, or another
compatible provider.

The database stores metadata and object keys. The object store stores bytes.

## Bucket/Folders

Recommended bucket:

```txt
leafletpilot-files
```

Recommended key structure:

```txt
markets/{marketId}/uploads/{yyyy}/{mm}/{fileId}-{originalName}
markets/{marketId}/products/{productId}/{fileId}.png
markets/{marketId}/templates/{templateId}/{fileId}.png
markets/{marketId}/campaigns/{campaignId}/previews/{fileId}.png
markets/{marketId}/campaigns/{campaignId}/exports/{fileId}.{ext}
```

Implemented local export key structure:

```txt
markets/{marketId}/campaigns/{campaignId}/exports/{exportJobId}/{safeFileName}.{ext}
```

Keep `marketId` in every object key to simplify tenant-level cleanup and audits.

## Original Uploads

Examples:

- Telegram image upload.
- Telegram document upload.
- Panel Excel upload.
- Panel product image upload before processing.

Database:

- `CampaignFile.file_type = original_upload` for campaign uploads.
- Product images should later use a shared `File` table or `ProductImage` linked metadata.

MVP:

- Store file metadata and object key.
- Do not parse Excel/PDF yet unless the implementation phase explicitly adds it.

## Product Images

Accepted MVP target:

- PNG preferred.
- Transparent background preferred but not required.
- Store dimensions and quality status.

Fields to track:

- `storage_key`
- `content_type`
- `size_bytes`
- `width`
- `height`
- `background_removed`
- `quality_status`

Later:

- Background removal.
- Image optimization.
- Duplicate detection.
- CDN cache.

## Brochure Previews

Preview files:

- `file_type = preview_png`
- `format = png`
- `status = ready`
- `page_number` for multi-page previews later

MVP:

- HTML preview is available through
  `GET /api/campaigns/{campaignId}/preview-html`.
- Do not create `CampaignFile` records for HTML preview reads.
- `POST /api/campaigns/{campaignId}/export-jobs` can create final PDF and PNG
  files from the same deterministic HTML renderer.

## Final Exports

Final formats:

- `brochure_pdf`
- `brochure_png`
- `instagram_post`
- Later: `instagram_story`, `facebook_post`, `whatsapp_image`

Each generated file should store:

- file type
- format
- status
- storage key
- signed URL or public URL policy
- size
- created timestamp
- sent timestamp
- last error

## Generated File Naming

Human-readable filename:

```txt
{marketSlug}-{campaignSlug}-{format}-{yyyyMMdd}.{ext}
```

Examples:

```txt
anadolu-market-hafta-28-a4.pdf
anadolu-market-hafta-28-page-1.png
anadolu-market-hafta-28-instagram-post.png
```

Object keys should still include UUIDs to avoid collisions.

## PDF/PNG Generation Plan

Current synchronous MVP flow:

1. API creates an `ExportJob` with `job_type` and `requested_formats`.
2. API marks it `running`.
3. API loads campaign, campaign items, and template config.
4. Template renderer creates deterministic HTML/CSS.
5. Playwright sync rendering runs in a background thread and generates PDF/PNG
   from that HTML.
6. API stores local bytes and `CampaignFile` metadata.
7. API validates each generated file exists and is non-empty.
8. API marks the `ExportJob` completed or failed. Failed jobs include
   `error_message` in API responses and log the full backend stack trace.

Future worker flow:

1. API creates a queued `ExportJob`.
2. Worker picks queued jobs.
3. Worker runs the same deterministic render service.
4. Worker uploads bytes to S3-compatible storage and stores object keys.
5. Worker marks the `ExportJob` completed or failed.

Template renderer inputs:

- market branding
- template metadata
- campaign title/date
- product list
- product images
- currency/language
- output format

## Playwright Export Later

Use Playwright for:

- PDF output with print CSS.
- High-resolution PNG screenshots.
- Multi-page rendering.

Playwright is now used by the backend export service. The Vite frontend only
calls API endpoints and is not coupled to renderer internals.

S3 remains deferred because the MVP now proves generated bytes locally without
adding credentials, bucket policy, signed URL, or cleanup complexity.

## Manual Smoke Test

1. Run migrations and seed development data.
2. Start the backend.
3. Call `GET /api/campaigns/{campaignId}/preview-html` with `X-Market-Id`.
4. Confirm the response includes `campaign_id`, `template_id`, `template_name`,
   `html`, and `generated_at`.
5. Confirm product names and prices appear in the returned HTML.
6. Create an export job with `requested_formats=["pdf","png"]`.
7. Confirm local files appear under `backend/storage/...` or the configured
   `LOCAL_STORAGE_DIR`.
8. Confirm campaign detail includes `CampaignFile` rows.
9. Download the PDF and PNG through
   `GET /api/campaigns/{campaignId}/files/{fileId}/download`.

## Cleanup And Retention

MVP defaults:

- Original uploads: keep 180 days.
- Preview files: keep 90 days.
- Final exports: keep 365 days.
- Failed temporary files: delete after 7 days.

Later:

- Per-plan retention.
- Admin cleanup jobs.
- Legal deletion request workflow.

## Security Considerations

- Buckets should be private by default.
- Use signed URLs for downloads.
- Never trust user-provided filenames as object keys.
- Validate content type and file size.
- Restrict file access by market membership.
- Store provider secrets outside database or encrypted at rest.
- Later add virus scanning for uploads.
