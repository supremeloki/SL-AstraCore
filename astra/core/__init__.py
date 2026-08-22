__all__ = ["AstraCore"]


def __getattr__(name):
    if name == "AstraCore":
        from astra.core.astra_core import AstraCore
        return AstraCore
    raise AttributeError(name)
