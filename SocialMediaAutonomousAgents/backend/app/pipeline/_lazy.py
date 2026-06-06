"""Lazy proxies to avoid import cycles on package load."""


class _LazyAttr:
    def __init__(self, factory) -> None:
        self._factory = factory

    def __getattr__(self, name: str):
        return getattr(self._factory(), name)

    def __repr__(self) -> str:
        return repr(self._factory())
