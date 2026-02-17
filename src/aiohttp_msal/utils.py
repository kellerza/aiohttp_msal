"""Graph User Info."""

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any


def async_wrap[T, **P](
    func: Callable[P, T],
) -> Callable[P, Coroutine[None, None, T]]:
    """Wrap a function doing I/O to run in an executor thread."""

    @wraps(func)
    async def run(
        *args: Any,
        **kwargs: Any,
    ) -> T:
        return await asyncio.to_thread(func, *args, **kwargs)

    return run


class dict_property(property):
    """Property."""

    def __init__(self, dict_name: str, prop_name: str) -> None:
        """Initialize the property."""
        self.dict_name = dict_name
        self.prop_name = prop_name

    def __get__(self, instance: Any, owner: type | None = None, /) -> Any:
        """Getter."""
        return getattr(instance, self.dict_name, {}).get(self.prop_name, "")

    def __set__(self, instance: Any, value: Any, /) -> None:
        """Setter."""
        if value == "":
            getattr(instance, self.dict_name, {}).pop(self.prop_name, None)
        else:
            getattr(instance, self.dict_name, {}).__setitem__(self.prop_name, value)


def retry[T, **P](
    func: Callable[P, Coroutine[None, None, T]],
) -> Callable[P, Coroutine[None, None, T]]:
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
