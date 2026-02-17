"""Test utils."""

from aiohttp_msal.utils import async_wrap


async def test_async_wrap() -> None:
    """Test async_wrap."""

    @async_wrap
    def some_blocking_func(x: int) -> int:
        """Sync func."""
        return x * 2

    def more_blocking_func(x: int) -> int:
        """Sync func."""
        return x * 8

    the_res = await some_blocking_func(3)
    assert the_res == 6

    the_res = await async_wrap(more_blocking_func)(3)
    assert the_res == 24
