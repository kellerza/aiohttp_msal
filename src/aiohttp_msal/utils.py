"""Graph User Info."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar, Any
from functools import partial


T = TypeVar("T")
P = ParamSpec("P")


def async_wrap(
    func: Callable[..., T],
) -> Callable[..., Awaitable[T]]:
    """Wrap a function doing I/O to run in an executor thread."""

    @wraps(func)
    async def run(
        loop: asyncio.AbstractEventLoop | None = None,
        executor: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        if loop is None:
            loop = asyncio.get_event_loop()
        pfunc = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, pfunc)

    return run


def retry(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """Retry if tenacity is installed."""

    @wraps(func)
    async def _retry(*args: P.args, **kwargs: P.kwargs) -> T:
        """Retry the request."""
        retries = [2, 4, 8]
        while True:
            try:
                res = await func(*args, **kwargs)
                return res
            except Exception as err:
                if retries:
                    await asyncio.sleep(retries.pop())
                else:
                    raise err

    return _retry
