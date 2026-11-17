"""BTC ATM Short Straddle — entry point."""
from __future__ import annotations

import os

from dotenv import load_dotenv

from node import build_node


def main() -> None:
    load_dotenv()
    node = build_node(
        api_key=os.environ["API_KEY"],
        api_secret=os.environ["API_SECRET"],
    )
    try:
        node.run()
    finally:
        node.stop()
        node.dispose()


if __name__ == "__main__":
    main()
