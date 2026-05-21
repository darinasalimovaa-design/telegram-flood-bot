import asyncio

from bot import configure_webhook, shutdown


async def main():
    await configure_webhook()
    await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
