import urllib.parse
from typing import Any

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now as timezone_now

from zerver.decorator import require_server_admin
from zerver.models import Realm

from .models import FlaggedMessage


@require_server_admin
def flagged_messages_panel(request: HttpRequest) -> HttpResponse:
    status_filter = request.GET.get("status", FlaggedMessage.STATUS_PENDING)
    if status_filter not in {
        FlaggedMessage.STATUS_PENDING,
        FlaggedMessage.STATUS_DISMISSED,
        FlaggedMessage.STATUS_ACTIONED,
    }:
        status_filter = FlaggedMessage.STATUS_PENDING

    realm_id_str = request.GET.get("realm_id", "")
    realm_filter: int | None = int(realm_id_str) if realm_id_str.isdigit() else None

    flags_qs = FlaggedMessage.objects.select_related("realm", "sender").filter(status=status_filter)
    if realm_filter is not None:
        flags_qs = flags_qs.filter(realm_id=realm_filter)

    flags = list(flags_qs[:200])

    for flag in flags:
        flag.conversation_url = _build_conversation_url(flag)  # type: ignore[attr-defined]

    realms = list(Realm.objects.order_by("name").values("id", "name", "string_id"))
    counts = {
        s: FlaggedMessage.objects.filter(status=s).count()
        for s in [
            FlaggedMessage.STATUS_PENDING,
            FlaggedMessage.STATUS_DISMISSED,
            FlaggedMessage.STATUS_ACTIONED,
        ]
    }

    context: dict[str, Any] = {
        "flags": flags,
        "status_filter": status_filter,
        "realm_filter": realm_filter,
        "realms": realms,
        "counts": counts,
        "STATUS_PENDING": FlaggedMessage.STATUS_PENDING,
        "STATUS_DISMISSED": FlaggedMessage.STATUS_DISMISSED,
        "STATUS_ACTIONED": FlaggedMessage.STATUS_ACTIONED,
    }
    return render(request, "safechat_moderation/flagged_messages.html", context)


@require_server_admin
def review_flagged_message(request: HttpRequest, flag_id: int) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseBadRequest()

    new_status = request.POST.get("status", "")
    if new_status not in {
        FlaggedMessage.STATUS_PENDING,
        FlaggedMessage.STATUS_DISMISSED,
        FlaggedMessage.STATUS_ACTIONED,
    }:
        return HttpResponseBadRequest()

    flag = get_object_or_404(FlaggedMessage, id=flag_id)
    flag.status = new_status
    flag.reviewed_by = request.user  # type: ignore[assignment]
    flag.reviewed_at = timezone_now()
    flag.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    from django.shortcuts import redirect

    back = request.POST.get("next", "/moderation/")
    return redirect(back)


def _build_conversation_url(flag: FlaggedMessage) -> str:
    if flag.is_dm:
        return f"{flag.realm.url}/#narrow/dm/near/{flag.message_id}"

    if flag.stream_id is None:
        return f"{flag.realm.url}/#narrow/near/{flag.message_id}"

    stream_slug = f"{flag.stream_id}-{_slugify(flag.stream_name)}"
    topic_encoded = urllib.parse.quote(flag.topic_name, safe="")
    return (
        f"{flag.realm.url}/#narrow/channel/{stream_slug}"
        f"/topic/{topic_encoded}/near/{flag.message_id}"
    )


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "-")
