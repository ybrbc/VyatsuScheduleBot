import asyncio
from telegram.ext import Application, CommandHandler

from config import load_secrets
from bot.handlers import ping, update_schedule
from services.scheduler import check_schedule

from services import scheduler



async def main():
    secrets = load_secrets()

    app = Application.builder().token(secrets["TELEGRAM_TOKEN"]).build()
    app.bot_data["secrets"] = secrets
    app.bot_data["last_check_time"] = None

    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("update", update_schedule))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    while True:
        scheduler.secrets = secrets  # присваиваем глобально
        await check_schedule(app)
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())