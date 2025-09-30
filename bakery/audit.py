from __future__ import annotations

from typing import Any, Optional

from .models_audit import AuditLog


def _extract_ip(request) -> Optional[str]:
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def write_audit(request, action: str, instance, *, before: Any = None, after: Any = None) -> None:
    """Persist an audit entry for the given instance."""
    user = getattr(request, "user", None)
    actor = user if getattr(user, "is_authenticated", False) else None

    AuditLog.objects.create(
        actor=actor,
        action=(action or "").lower(),
        table=instance._meta.model_name,
        row_id=getattr(instance, "pk", None) or 0,
        before=before,
        after=after,
        ip=_extract_ip(request),
        ua=request.META.get("HTTP_USER_AGENT") if request else None
    )
