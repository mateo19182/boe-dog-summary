import argparse
import asyncio
import logging
import sys

from tg_summary.bot import send_summary
from tg_summary.interactive_bot import run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="BOE-DOG Summary Bot")
    parser.add_argument(
        "--mode",
        choices=["cron", "bot"],
        default="bot",
        help="Run mode: 'cron' for daily summaries, 'bot' for interactive mode (default: bot)",
    )

    args = parser.parse_args()

    if args.mode == "cron":
        # Run daily summary (existing behavior)
        logging.info("Running in cron mode - sending daily summaries...")
        asyncio.run(send_summary())
    else:
        # Run interactive bot with polling
        logging.info("Running in bot mode - starting interactive bot...")
        try:
            asyncio.run(run_bot())
        except KeyboardInterrupt:
            logging.info("Bot stopped by user")
            sys.exit(0)


if __name__ == "__main__":
    main()
