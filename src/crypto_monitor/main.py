from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from .config import load_config
from .service import build_and_run


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(build_and_run(load_config()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
