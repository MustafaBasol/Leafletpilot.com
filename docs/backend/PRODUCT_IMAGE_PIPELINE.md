# Product image pipeline

New market and global catalog uploads pass through `app.services.image_pipeline` before
they can be used by flyer rendering.

The pipeline:

- reads at most 10 MiB from the request stream;
- decodes PNG, JPEG, or WebP content with Pillow and verifies the declared MIME type;
- rejects corrupt, animated, decompression-bomb, and excessive-dimension inputs;
- applies EXIF orientation;
- trims only fully transparent outer canvas, then adds a small safe margin;
- preserves transparent content as PNG and uses a single high-quality JPEG encoding for
  opaque JPEG/WebP photography;
- bounds the normalized variant to 1600 px on its longest edge;
- stores the original and normalized variant under server-owned, content-addressed
  global or market namespaces.

Normalized flyer assets are immutable. Replacing or removing a catalog image changes the
database reference but does not delete the old bytes, because finalized campaign snapshots
may still reference them. A future retention job can garbage-collect assets only after it
has checked both live catalog rows and frozen campaign snapshots.

## Background removal boundary

Background removal is intentionally not implemented locally and no third-party image API
is called. The normalized asset is the renderer input boundary for a future optional cutout
provider. Such a provider must return a validated transparent PNG/WebP candidate, preserve
the original and normalized fallback, remain tenant-scoped, and fail closed to the ordinary
rectangular-photo presentation. Provider output must re-enter the same validation and
content-addressed storage path; renderers must never resolve mutable provider URLs directly.
