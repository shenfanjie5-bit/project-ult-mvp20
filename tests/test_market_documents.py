from pathlib import Path

from scripts import audit_market_documents as audit


def test_market_document_audit_extracts_html_text_and_pdf_pages(tmp_path: Path) -> None:
    root = tmp_path / "market_data"
    html_path = root / "news" / "cls_flash" / "2026" / "02" / "1_test.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text(
        """
        <html><head><title>测试标题</title><style>.x{}</style></head>
        <body><script>ignored()</script><article>这是可提取的新闻正文，包含足够长度用于通过短文本检查。600519 涨幅较大。市场资金围绕业绩、订单、产业链和估值修复展开讨论，文本长度足以证明正文抽取链路有效。</article></body></html>
        """,
        encoding="utf-8",
    )
    pdf_path = root / "announcements" / "688256" / "2026" / "03" / "sample.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(
        b"%PDF-1.7\n1 0 obj<</Type /Page>>endobj\n2 0 obj<</Type /Pages>>endobj\n%%EOF"
    )

    report = audit.build_report(root=root, sample_per_group=5, pdf_text_page_limit=1)

    assert report["summary"]["news_html_files"] == 1
    assert report["summary"]["news_html_selected"] == 1
    assert report["summary"]["news_html_sampled"] == 1
    assert report["summary"]["announcement_pdf_files"] == 1
    assert report["summary"]["announcement_pdf_selected"] == 1
    assert report["summary"]["announcement_pdf_sampled"] == 1
    assert report["summary"]["document_files_total"] == 2
    assert report["summary"]["documents_selected_for_extractability_sampling"] == 2
    assert report["summary"]["documents_successfully_parsed"] == 2
    assert report["summary"]["coverage_gaps"] == {
        "document_files_not_selected_for_extractability_sampling": 0,
        "selected_documents_without_successful_parse": 0,
        "news_html_files_not_selected": 0,
        "announcement_pdf_files_not_selected": 0,
        "bounded_document_sampling": False,
        "entity_event_signals_are_sample_based": False,
        "retained_samples_are_bounded": True,
    }
    assert report["summary"]["sampling_coverage"] == {
        "selected_document_ratio": 1.0,
        "successful_parse_ratio_of_total_documents": 1.0,
        "successful_parse_ratio_of_selected_documents": 1.0,
        "entity_signal_ratio_of_sampled_documents": 1.0,
        "event_keyword_ratio_of_sampled_documents": 0.5,
        "citation_preview_ratio_of_sampled_documents": 0.5,
    }
    assert report["summary"]["signal_counts"]["sampled_documents"] == 2
    assert report["summary"]["signal_counts"]["entity_signal_samples"] == 2
    assert report["summary"]["signal_counts"]["date_signal_samples"] == 2
    assert report["summary"]["signal_counts"]["event_keyword_samples"] == 1
    news_group = report["news"]["groups"][0]
    pdf_group = report["announcements"]["groups"][0]
    assert news_group["retained_sample_count"] == 1
    assert pdf_group["retained_sample_count"] == 1
    news_sample = news_group["samples"][0]
    pdf_sample = pdf_group["samples"][0]
    assert news_sample["title"] == "测试标题"
    assert news_sample["stock_code_hints"] == ["600519"]
    assert news_sample["entity_signal_present"] is True
    assert news_sample["event_signal_present"] is True
    assert set(news_sample["event_categories"]) >= {
        "fundamental",
        "market_movement",
        "order_product",
    }
    assert "600519" in news_sample["citation_preview"]
    assert news_group["issue_counts"] == {}
    assert pdf_sample["pdf_header_ok"] is True
    assert pdf_sample["pdf_version"] == "1.7"
    assert pdf_sample["estimated_page_count"] == 1
    assert pdf_sample["path_entity_code_hints"] == ["688256"]
    assert pdf_sample["entity_signal_present"] is True


def test_market_document_audit_reports_sampling_limits(tmp_path: Path) -> None:
    root = tmp_path / "market_data"
    for idx in range(3):
        html_path = root / "news" / "cls_flash" / "2026" / "02" / f"{idx}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            f"<html><head><title>标题{idx}</title></head>"
            f"<body>600519 业绩 增长 订单 风险 资金 正文内容足够长，用于抽样覆盖统计。</body></html>",
            encoding="utf-8",
        )

    report = audit.build_report(root=root, sample_per_group=1, pdf_text_page_limit=1)

    assert report["summary"]["news_html_files"] == 3
    assert report["summary"]["news_html_selected"] == 1
    assert report["summary"]["news_html_sampled"] == 1
    assert report["summary"]["document_files_total"] == 3
    assert report["summary"]["documents_selected_for_extractability_sampling"] == 1
    assert report["summary"]["documents_successfully_parsed"] == 1
    assert report["summary"]["coverage_gaps"][
        "document_files_not_selected_for_extractability_sampling"
    ] == 2
    assert report["summary"]["coverage_gaps"]["news_html_files_not_selected"] == 2
    assert report["summary"]["coverage_gaps"]["bounded_document_sampling"] is True
    assert (
        report["summary"]["coverage_gaps"]["entity_event_signals_are_sample_based"]
        is True
    )
    assert report["summary"]["sampling_coverage"]["selected_document_ratio"] == 0.3333
    group = report["news"]["groups"][0]
    assert group["selected_count"] == 1
    assert group["unselected_count"] == 2
    assert group["sampling_coverage"]["selected_file_ratio"] == 0.3333


def test_market_document_audit_can_parse_all_while_retaining_bounded_examples(
    tmp_path: Path,
) -> None:
    root = tmp_path / "market_data"
    for idx in range(3):
        html_path = root / "news" / "cls_flash" / "2026" / "02" / f"{idx}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            f"<html><head><title>标题{idx}</title></head>"
            f"<body>600519 业绩 增长 订单 风险 资金 正文内容足够长，用于全量解析统计。</body></html>",
            encoding="utf-8",
        )

    report = audit.build_report(
        root=root,
        sample_per_group=0,
        pdf_text_page_limit=1,
        retained_samples_per_group=1,
    )

    assert report["scan_mode"] == "full_market_document_extractability_entity_event_signals"
    assert report["summary"]["documents_selected_for_extractability_sampling"] == 3
    assert report["summary"]["documents_successfully_parsed"] == 3
    assert report["summary"]["retained_sample_examples"] == 1
    assert report["summary"]["coverage_gaps"][
        "document_files_not_selected_for_extractability_sampling"
    ] == 0
    assert report["summary"]["coverage_gaps"]["bounded_document_sampling"] is False
    assert (
        report["summary"]["coverage_gaps"]["entity_event_signals_are_sample_based"]
        is False
    )
    group = report["news"]["groups"][0]
    assert group["sampled_count"] == 3
    assert group["retained_sample_count"] == 1
    assert group["text_chars"]["min"] is not None


def test_market_document_audit_flags_short_html_and_bad_pdf(tmp_path: Path) -> None:
    root = tmp_path / "market_data"
    html_path = root / "news" / "ths_news" / "2026" / "02" / "short.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html><body>短</body></html>", encoding="utf-8")
    pdf_path = root / "announcements" / "688256" / "2026" / "03" / "bad.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"not a pdf")

    report = audit.build_report(root=root, sample_per_group=5, pdf_text_page_limit=1)

    news_group = report["news"]["groups"][0]
    pdf_group = report["announcements"]["groups"][0]
    assert news_group["issue_counts"] == {
        "missing_title": 1,
        "short_extracted_text": 1,
    }
    assert pdf_group["issue_counts"] == {
        "bad_pdf_header": 1,
        "no_estimated_pages": 1,
    }
