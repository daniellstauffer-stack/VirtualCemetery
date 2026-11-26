"""Private file storage backends for family media and isolated case evidence.

In local development, files live under `MEDIA_ROOT` (`local_media/`) and
`EVIDENCE_ROOT` (`local_evidence/`) and are NEVER exposed directly via public
static/media URLs — every file download goes through an authenticated Django
handler that rechecks current permissions.

In staging/production (`USE_GCS_STORAGE=True`), files are written to separate
private Google Cloud Storage buckets (`GCP_MEDIA_BUCKET` and
`GCP_EVIDENCE_BUCKET`), with narrower IAM access and object lifecycle expiration
on the evidence bucket.
"""
from __future__ import annotations

from pathlib import Path
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage


class _GCSPrivateStorage(Storage):
    """Minimal private Google Cloud Storage backend using google-cloud-storage."""

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self._client = None

    def _bucket(self):
        if self._client is None:
            from google.cloud import storage  # Lazy import so local dev works offline

            self._client = storage.Client(project=settings.GCP_PROJECT_ID)
        return self._client.bucket(self.bucket_name)

    def _open(self, name: str, mode: str = "rb"):
        blob = self._bucket().blob(name)
        data = blob.download_as_bytes()
        return ContentFile(data, name=name)

    def _save(self, name: str, content):
        blob = self._bucket().blob(name)
        content.seek(0)
        blob.upload_from_file(content)
        return name

    def delete(self, name: str):
        blob = self._bucket().blob(name)
        if blob.exists():
            blob.delete()

    def exists(self, name: str) -> bool:
        return self._bucket().blob(name).exists()

    def size(self, name: str) -> int:
        blob = self._bucket().blob(name)
        blob.reload()
        return blob.size or 0

    def url(self, name: str) -> str:
        raise PermissionError("Private files must be served through permission-checked views.")


class _DynamicLocalOrGCSStorage(Storage):
    """Delegates dynamically to either private GCS or a local root resolved from Django settings."""

    root_setting_name: str = "MEDIA_ROOT"
    bucket_setting_name: str = "GCP_MEDIA_BUCKET"
    url_error_message: str = "Private files must be served through permission-checked views."

    def _backend(self) -> Storage:
        if settings.USE_GCS_STORAGE:
            return _GCSPrivateStorage(getattr(settings, self.bucket_setting_name))
        root = Path(getattr(settings, self.root_setting_name))
        root.mkdir(parents=True, exist_ok=True)
        return FileSystemStorage(location=str(root), base_url=None)

    def _open(self, name, mode="rb"):
        return self._backend().open(name, mode)

    def _save(self, name, content):
        return self._backend().save(name, content)

    def delete(self, name):
        return self._backend().delete(name)

    def exists(self, name):
        return self._backend().exists(name)

    def size(self, name):
        return self._backend().size(name)

    def get_available_name(self, name, max_length=None):
        return self._backend().get_available_name(name, max_length=max_length)

    def url(self, name):
        raise PermissionError(self.url_error_message)


class PrivateMediaStorage(_DynamicLocalOrGCSStorage):
    """Stores original uploads and EXIF-stripped display copies privately."""

    root_setting_name = "MEDIA_ROOT"
    bucket_setting_name = "GCP_MEDIA_BUCKET"
    url_error_message = "Private media must be served through authenticated permission-checked views."


class IsolatedEvidenceStorage(_DynamicLocalOrGCSStorage):
    """Dedicated storage for death-verification evidence, isolated from media."""

    root_setting_name = "EVIDENCE_ROOT"
    bucket_setting_name = "GCP_EVIDENCE_BUCKET"
    url_error_message = "Case evidence may only be downloaded by assigned staff reviewers."


def get_evidence_storage() -> IsolatedEvidenceStorage:
    return IsolatedEvidenceStorage()


def get_media_storage() -> PrivateMediaStorage:
    return PrivateMediaStorage()
