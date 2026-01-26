"""
Webhook Routes - Telegram webhook endpoint (v2.0)
"""

import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from aiogram.types import Update

logger = logging.getLogger(__name__)

router = APIRouter()


class WebhookInfo(BaseModel):
    """Webhook info model."""
    url: str
    is_set: bool


class WebhookSetRequest(BaseModel):
    """Webhook set request."""
    url: str


@router.post("/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.

    Receives updates from Telegram via webhook and forwards them to the bot dispatcher.

    This endpoint does not require authentication as it is validated by Telegram.
    """
    bot = request.app.state.bot
    dispatcher = getattr(request.app.state, 'dispatcher', None)

    if bot is None:
        logger.error("Webhook received but bot is not initialized")
        raise HTTPException(status_code=503, detail="Bot not initialized")

    if dispatcher is None:
        logger.error("Webhook received but dispatcher is not initialized")
        raise HTTPException(status_code=503, detail="Dispatcher not initialized")

    try:
        # Get update data from request
        data = await request.json()

        # Create Update object
        update = Update.model_validate(data)

        # Process update through dispatcher
        await dispatcher.feed_webhook_update(bot, update)

        logger.debug(f"Webhook update processed: {update.update_id}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Return ok to Telegram even on error to avoid retries
        return {"status": "ok"}


@router.get("/telegram/info", response_model=WebhookInfo)
async def get_webhook_info(request: Request):
    """
    Get current webhook information.

    Returns:
        Current webhook URL and status
    """
    from app.web.middleware import required_auth

    await required_auth(request)

    bot = request.app.state.bot

    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        webhook_info = await bot.get_webhook_info()

        return WebhookInfo(
            url=webhook_info.url or "",
            is_set=webhook_info.url is not None
        )

    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/set")
async def set_webhook(request: Request, req: WebhookSetRequest):
    """
    Set Telegram bot webhook.

    Request body:
        url: Webhook URL (e.g., https://yourdomain.com/webhook/telegram)

    Returns:
        Webhook set result
    """
    from app.web.middleware import required_auth
    from app.web.app import set_webhook

    await required_auth(request)

    bot = request.app.state.bot

    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        success = await set_webhook(bot, req.url)

        if success:
            logger.info(f"Webhook set to: {req.url}")
            return {"status": "ok", "url": req.url}
        else:
            raise HTTPException(status_code=500, detail="Failed to set webhook")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/delete")
async def delete_webhook(request: Request):
    """
    Delete Telegram bot webhook.

    Returns:
        Webhook deletion result
    """
    from app.web.middleware import required_auth
    from app.web.app import delete_webhook

    await required_auth(request)

    bot = request.app.state.bot

    if bot is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        success = await delete_webhook(bot)

        if success:
            logger.info("Webhook deleted")
            return {"status": "ok"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete webhook")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def webhook_health():
    """
    Webhook health check.

    This is a simple GET endpoint that can be used to verify
    the webhook server is running.

    Returns:
        Webhook health status
    """
    return {
        "status": "ok",
        "service": "telegram-webhook",
        "version": "2.0.0"
    }
