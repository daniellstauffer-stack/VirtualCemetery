"""Security and privacy HTTP headers middleware.

Enforces the architecture requirement to prevent search indexing and shared
caching on all private planning, stewardship, staff, event, and restricted
memorial routes.
"""
from __future__ import annotations

RESTRICTED_PREFIXES = (
    "/plan/",
    "/stewardship/",
    "/events/",
    "/accounts/",
    "/jobs/",
    "/django-admin/",
    "/integrations/facebook/",
    "/integrations/contacts/",
)


class PrivacyAndSecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Prevent shared caching and indexing on restricted paths or whenever a
        # view explicitly marks the response as restricted (e.g., private memorials).
        is_restricted = (
            any(request.path.startswith(prefix) for prefix in RESTRICTED_PREFIXES)
            or getattr(response, "vc_restricted", False)
            or request.user.is_authenticated
        )

        if is_restricted:
            response["Cache-Control"] = "private, no-store, no-cache, must-revalidate"
            response["Pragma"] = "no-cache"
            if any(request.path.startswith(p) for p in RESTRICTED_PREFIXES) or getattr(
                response, "vc_restricted", False
            ):
                response["X-Robots-Tag"] = "noindex, nofollow, noarchive"

        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response
