"""Graph User Info."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial, wraps
from typing import Any, ParamSpec, TypeVar

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


# def dict_property(dict_name: str, prop_name: str) -> property:
#     """Create properties for a dictionary."""
#     return property(
#         fget=lambda self: str(getattr(self, dict_name).get(prop_name, "")),
#         fset=lambda self, v: getattr(self, dict_name).set(prop_name, v),
#         fdel=lambda self: getattr(self, dict_name).pop(prop_name, None),
#         doc=f'self.{dict_name}["{prop_name}"]',
#     )


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
