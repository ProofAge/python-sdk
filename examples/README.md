# Examples

Runnable examples of the ProofAge Python SDK. Each one creates a verification link for a user and
receives the decision by webhook; they use a **test** workspace, which is never billed. Keys come
from `PROOFAGE_API_KEY` and `PROOFAGE_SECRET_KEY`, and the workspace's webhook URL must point at
your running example (a tunnel such as ngrok works while developing).

| Example | What it shows | Install |
|---|---|---|
| [`aiogram_bot/`](aiogram_bot/bot.py) | A Telegram bot: `/verify` sends the link, the webhook messages the user the outcome. The chat id is the session's `external_id`, so no database is needed | `pip install proofage aiogram` |
| [`fastapi_app/`](fastapi_app/main.py) | Creating a link from a route, and the `ProofAgeWebhook` dependency | `pip install "proofage[fastapi]" uvicorn` |
| [`django_view/`](django_view/views.py) | A login-protected view that redirects to the link, and `@proofage_webhook` | `pip install "proofage[django]"` |

The bot is the seed of a deployable Telegram bot template.
