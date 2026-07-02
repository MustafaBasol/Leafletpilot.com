# File Storage And Export Plan

## Storage Provider

Use S3-compatible object storage so the backend can run against AWS S3, Cloudflare R2, Supabase Storage, MinIO, or another compatible provider.

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

- Create records when preview generation is requested.
- Real preview rendering can wait for export implementation phase.

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

Later export architecture:

1. Campaign data is normalized into a render payload.
2. Template renderer creates HTML/CSS.
3. Playwright opens the render route or HTML file.
4. Playwright exports PDF or screenshots.
5. Files are uploaded to object storage.
6. `CampaignFile` records are marked ready.

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

Do not add Playwright backend code before the export phase. The current Vite frontend should not be coupled to export rendering.

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
