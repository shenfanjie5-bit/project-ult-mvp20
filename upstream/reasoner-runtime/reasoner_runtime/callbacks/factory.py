from __future__ import annotations

from functools import lru_cache

from reasoner_runtime.callbacks.base import CallbackBackend
from reasoner_runtime.callbacks.langfuse import LangfuseCallbackBackend
from reasoner_runtime.callbacks.otel import OTELCallbackBackend
from reasoner_runtime.config.models import CallbackProfile


def build_callback_backends(
    profile: CallbackProfile | None,
) -> tuple[CallbackBackend, ...]:
    if profile is None:
        return ()

    return _build_callback_backends_cached(
        profile.backend,
        profile.endpoint,
        profile.enabled,
    )


@lru_cache(maxsize=16)
def _build_callback_backends_cached(
    backend: str,
    endpoint: str | None,
    enabled: bool,
) -> tuple[CallbackBackend, ...]:
    if not enabled or backend == "none":
        return ()

    if backend == "otel":
        return (OTELCallbackBackend(),)

    if backend == "langfuse":
        return (LangfuseCallbackBackend(host=endpoint),)

    raise ValueError(f"unsupported callback backend: {backend}")
