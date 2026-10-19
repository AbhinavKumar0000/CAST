"""anyio compatibility shim for the ``mcp`` client/server on this environment.

``mcp`` 1.22 subscribes to the generic factory as
``anyio.create_memory_object_stream[T](0)``. The installed ``anyio`` (3.7.1) exposes
that name as a plain function, so the subscript raises
``TypeError: 'function' object is not subscriptable``. The type parameter is purely
typing; at runtime the call is identical to ``anyio.create_memory_object_stream(0)``.

:func:`install` replaces the module-level name with a small class that supports both
``create_memory_object_stream(...)`` and ``create_memory_object_stream[...](...)``.
All ``mcp`` call sites reference the attribute as ``anyio.create_memory_object_stream``
(never a ``from anyio import ...`` alias), so replacing the attribute is sufficient and
takes effect whenever an ``mcp`` code path runs. No environment or package changes.
"""

from __future__ import annotations

_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    import anyio

    factory = anyio.create_memory_object_stream
    if hasattr(factory, "__class_getitem__"):
        _installed = True
        return

    class _MemoryObjectStreamFactory:
        def __new__(cls, *args, **kwargs):  # noqa: D102
            return factory(*args, **kwargs)

        @classmethod
        def __class_getitem__(cls, _item):  # noqa: D102
            return factory

    anyio.create_memory_object_stream = _MemoryObjectStreamFactory  # type: ignore[assignment]
    _installed = True
