import asyncio

from src.mcp_server import run_server


def main():
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
