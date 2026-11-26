"""Private HTTP worker endpoints invoked by Google Cloud Tasks / Cloud Scheduler."""
from __future__ import annotations

import hmac
import json
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .tasks import (
    deliver_funeral_invitation,
    process_plan_memory_photo,
    purge_expired_case_evidence,
)


def _is_authorized_worker_request(request) -> bool:
    """Validate Cloud Tasks/Scheduler authorization.

    In Cloud Run, IAM restricts the private worker service so ONLY the Cloud
    Tasks delivery service account can invoke it. We additionally verify a
    shared secret header when configured for defense-in-depth and local tests.
    """
    expected = settings.WORKER_SHARED_SECRET
    provided = request.headers.get("X-VC-Worker-Secret", "")
    if expected and provided and hmac.compare_digest(expected, provided):
        return True
    # Cloud Run strips spoofing of X-CloudTasks-QueueName when private IAM is enforced
    if settings.CLOUD_TASKS_ENABLED and request.headers.get("X-CloudTasks-QueueName") == settings.GCP_TASKS_QUEUE_NAME:
        return True
    return False


@csrf_exempt
@require_POST
def process_photo_endpoint(request):
    if not _is_authorized_worker_request(request):
        return HttpResponseForbidden("Unauthorized worker request.")
    data = json.loads(request.body.decode("utf-8") or "{}")
    ok = process_plan_memory_photo(data.get("memory_id", ""))
    return JsonResponse({"processed": ok})


@csrf_exempt
@require_POST
def send_invitation_endpoint(request):
    if not _is_authorized_worker_request(request):
        return HttpResponseForbidden("Unauthorized worker request.")
    data = json.loads(request.body.decode("utf-8") or "{}")
    status = deliver_funeral_invitation(data.get("delivery_id", ""))
    return JsonResponse({"status": status})


@csrf_exempt
@require_POST
def purge_evidence_endpoint(request):
    if not _is_authorized_worker_request(request):
        return HttpResponseForbidden("Unauthorized worker request.")
    count = purge_expired_case_evidence()
    return JsonResponse({"purged": count})
