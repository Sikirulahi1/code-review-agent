from __future__ import annotations

import random
import time
from collections.abc import Callable
from logging import Logger
from typing import TypeVar

T = TypeVar("T")


def run_with_exponential_backoff(
    operation: Callable[[], T],
    *,
    retry_attempts: int,
    backoff_max_seconds: float,
    should_retry: Callable[[Exception], bool],
    logger: Logger | None = None,
    retry_log_template: str | None = None,
    jitter_max_seconds: float = 0.0,
) -> T:
    delay = 1.0
    max_backoff = max(1.0, float(backoff_max_seconds))
    max_attempts = max(1, int(retry_attempts))

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == max_attempts or not should_retry(exc):
                raise

            jitter = random.uniform(0.0, max(0.0, jitter_max_seconds))
            wait_seconds = min(delay + jitter, max_backoff)

            if logger and retry_log_template:
                logger.warning(retry_log_template, wait_seconds, attempt)

            time.sleep(wait_seconds)
            delay = min(delay * 2, max_backoff)

    raise RuntimeError("unreachable")
