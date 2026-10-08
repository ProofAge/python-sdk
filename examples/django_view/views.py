"""Django views: send a logged-in user to ProofAge, and receive the decision.

    pip install "proofage[django]"

Wire them in urls.py:

    path("verify/", views.start), path("webhooks/proofage/", views.webhook)

and set your workspace's webhook URL to https://<public host>/webhooks/proofage/. The keys come
from PROOFAGE_API_KEY and PROOFAGE_SECRET_KEY (or pass them to `@proofage_webhook(...)`).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from proofage import ProofAge, VerificationStatus, WebhookEventType
from proofage.integrations.django import proofage_webhook

client = ProofAge()  # one client (and connection pool) for the whole process


@login_required
def start(request: HttpRequest) -> HttpResponse:
    """Create a session for the logged-in user and send them to it."""
    verification = client.verifications.create(external_id=str(request.user.pk))
    return HttpResponseRedirect(verification.url)


@proofage_webhook
def webhook(request: HttpRequest) -> HttpResponse:
    """ProofAge calls this with the decision; `request.proofage_event` is already verified."""
    event = request.proofage_event
    if event.event == WebhookEventType.DATA_UPDATED:
        return HttpResponse(status=200)  # corrected document fields, not a decision
    if event.status == VerificationStatus.APPROVED:
        ...  # e.g. mark User(pk=event.external_id) as verified, keyed on event.delivery_id
    return HttpResponse(status=200)
