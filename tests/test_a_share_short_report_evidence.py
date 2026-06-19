from pathlib import Path

from scripts import audit_a_share_short_report_evidence as audit


def _write_html(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<html><head><title>{title}</title></head><body>{body}</body></html>",
        encoding="utf-8",
    )


def test_short_report_evidence_scans_strict_direct_and_noise(tmp_path: Path) -> None:
    market_root = tmp_path / "market_data"
    universe_path = tmp_path / "universe.yaml"
    universe_path.write_text(
        """
constituents:
  - ts_code: 688256.SH
    industry_ids: [AI_CHIP]
""".lstrip(),
        encoding="utf-8",
    )
    _write_html(
        market_root / "news" / "cls_flash" / "2026" / "02" / "direct.html",
        "做空机构发布做空报告指控寒武纪-U",
        "某做空机构发布做空报告，指控寒武纪-U(688256)存在收入确认风险。",
    )
    _write_html(
        market_root / "news" / "cls_flash" / "2026" / "02" / "foreign.html",
        "香橼称正在做空闪迪",
        "知名做空机构香橼称正在做空闪迪，相关空头观点影响海外科技股。",
    )
    _write_html(
        market_root / "news" / "eastmoney_guba" / "2026" / "02" / "noise.html",
        "严查做空机构",
        "严查做空机构，小散没这能力。",
    )
    _write_html(
        market_root / "news" / "cls_flash" / "2026" / "02" / "related.html",
        "商务部新闻发言人答记者问",
        "正文是关税新闻。相关阅读：做空机构香橼资本突袭闪迪。",
    )

    report = audit.build_report(
        market_root=market_root,
        universe_path=universe_path,
        retained_sample_limit=5,
    )

    summary = report["summary"]
    assert summary["news_html_files_scanned"] == 4
    assert summary["parse_error_count"] == 0
    assert summary["strict_short_report_documents"] == 2
    assert summary["direct_a_share_short_report_documents"] == 1
    assert summary["foreign_or_market_short_report_documents"] == 1
    assert summary["direct_a_share_ts_code_count"] == 1
    assert summary["direct_a_share_top_ts_codes"] == {"688256.SH": 1}
    assert summary["candidate_evidence_ready"] is True
    assert summary["strict_source_counts"] == {"news/cls_flash": 2}

    assert report["direct_a_share_samples"][0]["a_share_ts_codes"] == ["688256.SH"]
    assert report["foreign_or_market_samples"][0]["source"] == "news/cls_flash"
    assert "eastmoney_guba" not in summary["strict_source_counts"]

    rendered = audit.render_markdown(report)
    assert "Direct A-share short-report documents: `1`" in rendered
    assert "688256.SH" in rendered
