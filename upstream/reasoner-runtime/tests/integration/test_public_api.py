from __future__ import annotations

import reasoner_runtime


def test_top_level_public_api_exports_runtime_contracts() -> None:
    expected_exports = {
        "CallbackProfile",
        "FailureClass",
        "FallbackDecision",
        "HealthCheckReport",
        "ProviderHealthStatus",
        "ProviderProfile",
        "QuotaStatus",
        "ReasonerRequest",
        "ReplayBundle",
        "StructuredGenerationResult",
        "build_client",
        "build_replay_bundle",
        "classify_failure",
        "generate_structured",
        "generate_structured_with_replay",
        "health_check",
        "scrub_input",
    }

    assert expected_exports <= set(reasoner_runtime.__all__)
    for name in expected_exports:
        assert getattr(reasoner_runtime, name) is not None

    assert callable(reasoner_runtime.generate_structured)
    assert callable(reasoner_runtime.generate_structured_with_replay)
    assert callable(reasoner_runtime.health_check)
    assert callable(reasoner_runtime.build_client)
    assert callable(reasoner_runtime.scrub_input)
    assert callable(reasoner_runtime.build_replay_bundle)
    assert callable(reasoner_runtime.classify_failure)
