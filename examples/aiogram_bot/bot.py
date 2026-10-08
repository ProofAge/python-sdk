"""A Telegram bot that verifies a user with ProofAge and tells them the outcome.

`/verify` creates a session and sends the link; ProofAge then POSTs the decision to
`/webhooks/proofage`, which messages the user. The user's Telegram chat id is the session's
`external_id`, so the webhook knows who to write to without a database.

Run it:

    pip install proofage aiogram
    export PROOFAGE_API_KEY=pk_test_...  PROOFAGE_SECRET_KEY=sk_test_...
    export TELEGRAM_BOT_TOKEN=123456:ABC...
    python examples/aiogram_bot/bot.py

and set your workspace's webhook URL to https://<public host>/webhooks/proofage.
"""

from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiohttp import web

from proofage import (
    AsyncProofAge,
    VerificationStatus,
    WebhookEventType,
    WebhookVerificationError,
    verify_webhook,
)

OUTCOMES = {
    VerificationStatus.APPROVED.value: "Thanks, your check is complete.",
    VerificationStatus.DECLINED.value: "Sorry, we could not verify you.",
    VerificationStatus.RESUBMISSION_REQUESTED.value: "Please try again with /verify.",
}


async def start_verification(client: AsyncProofAge, chat_id: int) -> str:
    """Create a session for this chat and return the message that carries its link."""
    verification = await client.verifications.create(external_id=str(chat_id))
    return f"Open this link on your phone to verify yourself:\n{verification.url}"


def build_dispatcher(client: AsyncProofAge) -> Dispatcher:
    dispatcher = Dispatcher()

    @dispatcher.message(Command("verify"))
    async def verify(message: Message) -> None:
        await message.answer(await start_verification(client, message.chat.id))

    return dispatcher


def build_webhook_app(bot: Bot) -> web.Application:
    """The endpoint ProofAge calls with the decision."""
    delivered: set[str] = set()  # a real bot keeps this in a database or cache

    async def handle(request: web.Request) -> web.Response:
        try:
            event = verify_webhook(await request.read(), request.headers)
        except WebhookVerificationError as error:
            return web.json_response(
                {"error": {"code": error.code, "message": error.message}}, status=error.http_status
            )
        # Corrected document fields are not a decision: nothing to tell the user.
        if event.event == WebhookEventType.DATA_UPDATED:
            return web.Response(status=200)
        # Sessions made elsewhere (the console, another integration) have their own external_id.
        if event.external_id is None or not event.external_id.lstrip("-").isdigit():
            return web.Response(status=200)
        # A delivery can arrive more than once: its id is the same on every retry.
        if event.delivery_id in delivered:
            return web.Response(status=200)

        text = OUTCOMES.get(str(event.status))
        if text is not None:
            # If this raises, ProofAge retries the delivery (500), so remember it only afterwards.
            await bot.send_message(int(event.external_id), text)
        if event.delivery_id:
            delivered.add(event.delivery_id)
        return web.Response(status=200)

    app = web.Application()
    app.router.add_post("/webhooks/proofage", handle)
    return app


async def main() -> None:
    bot = Bot(os.environ["TELEGRAM_BOT_TOKEN"])
    runner = web.AppRunner(build_webhook_app(bot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", "8080"))).start()
    try:
        async with AsyncProofAge() as client:
            await build_dispatcher(client).start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
