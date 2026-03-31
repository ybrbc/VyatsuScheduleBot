from telegram.ext import Application, CommandHandler

from config import SECRETS
from bot.handlers import ping, update_schedule, print_schedule
from services.scheduler import check_schedule


def main():
    app = Application.builder().token(SECRETS["TELEGRAM_TOKEN"]).build()
    app.bot_data["last_check_time"] = None
    app.bot_data["is_updating"] = False

    app.add_handler(CommandHandler("ping", ping, block=False))
    app.add_handler(CommandHandler("update", update_schedule, block=False))
    app.add_handler(CommandHandler("print", print_schedule, block=False))

    app.job_queue.run_repeating(check_schedule, interval=3600, first=1)

    app.run_polling()

if __name__ == "__main__":
    main()