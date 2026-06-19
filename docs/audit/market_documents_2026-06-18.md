# Market document extractability audit

- Generated at: `2026-06-18T22:23:49+0800`
- Root: `/Volumes/dockcase2tb/market_data`
- Scan mode: `full_market_document_extractability_entity_event_signals`
- Sample per group: `0`
- Retained samples per group: `20`

## Summary

| Metric | Value |
|---|---:|
| `news_html_files` | `14956` |
| `news_html_selected` | `14956` |
| `news_html_sampled` | `14956` |
| `announcement_pdf_files` | `198` |
| `announcement_pdf_selected` | `198` |
| `announcement_pdf_sampled` | `198` |
| `document_files_total` | `15154` |
| `documents_selected_for_extractability_sampling` | `15154` |
| `documents_successfully_parsed` | `15154` |
| `retained_sample_examples` | `80` |
| `issue_counts` | `{'boilerplate_or_placeholder_text': 32, 'missing_title': 29, 'short_extracted_text': 24, 'short_pdf_text_extract': 6}` |
| `signal_counts` | `{'citation_preview_samples': 15136, 'date_signal_samples': 15154, 'entity_signal_samples': 6724, 'event_keyword_samples': 15117, 'sampled_documents': 15154}` |
| `event_category_counts` | `{'capital_action': 2213, 'fundamental': 8588, 'market_movement': 10323, 'order_product': 13969, 'risk_regulatory': 15031}` |

## Sampling Coverage

| Metric | Value |
|---|---:|
| `selected_document_ratio` | `1.0` |
| `successful_parse_ratio_of_total_documents` | `1.0` |
| `successful_parse_ratio_of_selected_documents` | `1.0` |
| `entity_signal_ratio_of_sampled_documents` | `0.4437` |
| `event_keyword_ratio_of_sampled_documents` | `0.9976` |
| `citation_preview_ratio_of_sampled_documents` | `0.9988` |

| Coverage gap | Count / flag |
|---|---:|
| `document_files_not_selected_for_extractability_sampling` | `0` |
| `selected_documents_without_successful_parse` | `0` |
| `news_html_files_not_selected` | `0` |
| `announcement_pdf_files_not_selected` | `0` |
| `bounded_document_sampling` | `False` |
| `entity_event_signals_are_sample_based` | `False` |
| `retained_samples_are_bounded` | `True` |

## Source Group Coverage

| Source | Files | Selected | Parsed | Retained examples | Unselected | Selected parse misses | Selected ratio | Parse ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `news/cls_flash` | 14300 | 14300 | 14300 | 20 | 0 | 0 | 1.0 | 1.0 |
| `news/eastmoney_guba` | 584 | 584 | 584 | 20 | 0 | 0 | 1.0 | 1.0 |
| `news/ths_news` | 72 | 72 | 72 | 20 | 0 | 0 | 1.0 | 1.0 |
| `announcements/688256` | 198 | 198 | 198 | 20 | 0 | 0 | 1.0 | 1.0 |

## Entity/Event Signals

| Source | Sampled | Entity signal | Date signal | Event keyword | Citation preview | Event categories |
|---|---:|---:|---:|---:|---:|---|
| `news/cls_flash` | 14300 | 5900 | 14300 | 14299 | 14300 | capital_action=2038, fundamental=8413, market_movement=10146, order_product=13279, risk_regulatory=14299 |
| `news/eastmoney_guba` | 584 | 584 | 584 | 584 | 584 | capital_action=33, fundamental=90, market_movement=76, order_product=584, risk_regulatory=567 |
| `news/ths_news` | 72 | 42 | 72 | 54 | 60 | capital_action=16, fundamental=36, market_movement=23, order_product=33, risk_regulatory=46 |
| `announcements/688256` | 198 | 198 | 198 | 180 | 192 | capital_action=126, fundamental=49, market_movement=78, order_product=73, risk_regulatory=119 |

## News HTML

| Group | Files | Selected | Parsed | Months | Text chars median | Issues |
|---|---:|---:|---:|---|---:|---|
| `cls_flash` | 14300 | 14300 | 14300 | 2026-02, 2026-03 | 1487.0 | {'short_extracted_text': 1} |
| `eastmoney_guba` | 584 | 584 | 584 | 2026-02 | 829.0 | {'boilerplate_or_placeholder_text': 17, 'missing_title': 17} |
| `ths_news` | 72 | 72 | 72 | 2026-02, 2026-03 | 1032.0 | {'boilerplate_or_placeholder_text': 15, 'missing_title': 12, 'short_extracted_text': 23} |

## Announcement PDFs

| Group | Files | Selected | Parsed | Months | Page median | Sample text median | Issues |
|---|---:|---:|---:|---|---:|---:|---|
| `688256` | 198 | 198 | 198 | 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-01, 2026-02, 2026-03 | 6.0 | 1357.0 | {'short_pdf_text_extract': 6} |

## Notes

- HTML extraction uses generic tag/script/style removal and is intended to prove bounded text extractability, not perfect article parsing.
- PDF extraction records header/page metadata and uses optional `pdfplumber` text extraction when available; failures are reported per selected sample.
- Entity/date/event signals were computed for every audited HTML/PDF file; retained `samples` are bounded only to keep the JSON reviewable.
