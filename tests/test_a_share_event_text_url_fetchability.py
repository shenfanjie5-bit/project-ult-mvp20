import json
from pathlib import Path

from scripts import audit_a_share_event_text_url_fetchability as audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _classification_row(dp_id: str, url: str, title: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "risk_discount",
        "source_dependencies": ["L9.media.report"],
        "headline_inputs": [
            {
                "dependency_dp_id": "L9.media.report",
                "title": title,
                "url": url,
                "source": "unit",
                "time": "2026-06-19T01:00:00",
            }
        ],
    }


def _pre_row(dp_id: str) -> dict:
    return {
        "dp_id": dp_id,
        "score_target": "risk_discount",
        "screening_status": "screened_target_and_transmission_keyword_hit_requires_review",
    }


def _html(title: str, body: str) -> str:
    return f"""
    <html>
      <head><title>{title}</title><meta name="description" content="{title}" /></head>
      <body><script>ignore()</script><main>打开APP {body} 财联社声明：仅供参考。</main></body>
    </html>
    """


def test_url_fetchability_maps_body_evidence_without_known_writes(tmp_path: Path) -> None:
    classification_path = tmp_path / "classification.json"
    pre_path = tmp_path / "pre.json"
    _write_json(
        classification_path,
        {
            "rows": [
                _classification_row(
                    "L8.shock.supply_break",
                    "https://example.test/supply",
                    "霍尔木兹海峡航运受阻",
                ),
                _classification_row(
                    "L0.policy.tax_trade",
                    "https://example.test/tax",
                    "出口管制冲击A股上市公司供应链",
                ),
            ]
        },
    )
    _write_json(
        pre_path,
        {"rows": [_pre_row("L8.shock.supply_break"), _pre_row("L0.policy.tax_trade")]},
    )

    def fetcher(url: str, timeout: float) -> audit.FetchResult:
        if url.endswith("/supply"):
            return audit.FetchResult(
                url=url,
                ok=True,
                status=200,
                content_type="text/html",
                html_text=_html("霍尔木兹海峡航运受阻", "霍尔木兹海峡商业航运恢复，暂未看到相关传导。"),
            )
        return audit.FetchResult(
            url=url,
            ok=True,
            status=200,
            content_type="text/html",
            html_text=_html("出口管制冲击A股上市公司供应链", "出口管制冲击A股上市公司供应链和人民币结算。"),
        )

    report = audit.build_report(
        classification_inputs_path=classification_path,
        preclassification_path=pre_path,
        fetcher=fetcher,
    )

    assert report["summary"]["unique_url_count"] == 2
    assert report["summary"]["fetch_success_count"] == 2
    assert report["summary"]["primary_text_available_url_count"] == 2
    assert report["summary"]["body_packet_count"] == 2
    assert report["summary"]["body_target_hit_packet_count"] == 2
    assert report["summary"]["body_direct_transmission_hit_packet_count"] == 1
    assert report["summary"]["body_signal_sufficient_for_classifier_count"] == 1
    assert report["summary"]["known_candidate_allowed_count"] == 0
    assert report["summary"]["production_write_allowed_count"] == 0
    rows = {row["dp_id"]: row for row in report["rows"]}
    assert rows["L0.policy.tax_trade"]["body_signal_sufficient_for_classifier"] is True
    assert rows["L0.policy.tax_trade"]["known_candidate_allowed"] is False
    assert rows["L8.shock.supply_break"]["body_signal_sufficient_for_classifier"] is False
    assert rows["L8.shock.supply_break"]["safe_to_upsert_without_review"] is False
    assert "Unique URLs: `2`" in audit.render_markdown(report)


def test_url_fetchability_keeps_fetch_failures_conservative(tmp_path: Path) -> None:
    classification_path = tmp_path / "classification.json"
    pre_path = tmp_path / "pre.json"
    _write_json(
        classification_path,
        {
            "rows": [
                _classification_row(
                    "L8.shock.black_swan",
                    "https://example.test/down",
                    "纽约时报广场发生枪击",
                )
            ]
        },
    )
    _write_json(pre_path, {"rows": [_pre_row("L8.shock.black_swan")]})

    def fetcher(url: str, timeout: float) -> audit.FetchResult:
        return audit.FetchResult(url=url, ok=False, error="URLError:timeout")

    report = audit.build_report(
        classification_inputs_path=classification_path,
        preclassification_path=pre_path,
        fetcher=fetcher,
    )

    assert report["summary"]["fetch_success_count"] == 0
    assert report["summary"]["fetch_failure_count"] == 1
    assert report["summary"]["body_text_available_packet_count"] == 0
    assert report["summary"]["body_signal_sufficient_for_classifier_count"] == 0
    assert report["rows"][0]["body_status"] == "body_unavailable"
