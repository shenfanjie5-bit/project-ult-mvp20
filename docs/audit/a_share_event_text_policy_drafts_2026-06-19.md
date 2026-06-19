# A-share event-text policy drafts

- Generated: `2026-06-19T12:11:48+08:00`
- Event-text tasks: `12`
- Draft Known review packets: `10`
- Draft Unknown packets: `2`
- Draft contracts valid: `12`
- Draft contracts invalid: `0`
- Known drafts bridge-validated: `10`
- Safe to upsert without review: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Draft Status Counts

| Status | Count |
|---|---:|
| `draft_known_market_doc_review_required` | 10 |
| `unknown_market_doc_clean_evidence_required` | 1 |
| `unknown_market_doc_evidence_required` | 1 |

## Rows

| dp_id | target | draft status | data status | contract | confidence | value |
|---|---|---|---|---:|---:|---|
| `L0.compete.new_entrant` | `fundamental_score` | `unknown_market_doc_evidence_required` | `Unknown` | yes | 0.0 | `{"blocked_reason": "market_doc_direct_transmission_link_required", "required_policy": "same-sentence or same-paragraph direct A-share transmission link; reviewed direction and magnitude after the link is found", "review_required": true}` |
| `L0.compete.price_war` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.46 | `{"components": {"classification": "competitive_price_pressure", "direct_transmission_hits": ["供应链", "出口", "板块", "进口"], "market_doc_examples": 3, "same_sentence_evidence_count": 3, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["价格战", "促销", "打价格", "降价"]}, "drivers": ["market_doc:price_war", "L9.industry.compete_risk"], "score": -0.25}` |
| `L0.compete.share_concentration` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.44 | `{"components": {"classification": "leader_share_or_consolidation", "direct_transmission_hits": ["上市公司", "产业链", "供应链", "出口", "板块"], "market_doc_examples": 5, "same_sentence_evidence_count": 5, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["出清", "市占率", "市场份额"]}, "drivers": ["market_doc:share_concentration", "L9.industry.compete_risk"], "score": 0.22}` |
| `L0.policy.access_license` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.43 | `{"components": {"classification": "license_or_access_tightening", "direct_transmission_hits": ["A股", "上市公司", "产业链", "出口"], "market_doc_examples": 5, "same_sentence_evidence_count": 9, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["备案", "许可", "资质"]}, "drivers": ["market_doc:access_license", "L9.industry.policy_change"], "score": -0.2}` |
| `L0.policy.regulation` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.41 | `{"components": {"classification": "regulatory_or_compliance_event", "direct_transmission_hits": ["A股", "上市公司", "产业链", "出口"], "market_doc_examples": 5, "same_sentence_evidence_count": 6, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["制裁", "合规", "处罚", "监管", "调查", "问询"]}, "drivers": ["market_doc:regulation", "L9.industry.policy_change", "L9.media.report"], "score": -0.12}` |
| `L0.policy.subsidy` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.4 | `{"components": {"classification": "subsidy_or_countervailing_policy", "direct_transmission_hits": ["A股", "供应链", "出口", "进口"], "market_doc_examples": 5, "same_sentence_evidence_count": 7, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["补贴"]}, "drivers": ["market_doc:subsidy", "L9.industry.policy_change", "L9.media.report"], "score": -0.1}` |
| `L0.policy.tax_trade` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.42 | `{"components": {"classification": "tariff_or_trade_friction", "direct_transmission_hits": ["出口", "进口"], "market_doc_examples": 5, "same_sentence_evidence_count": 5, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["关税"]}, "drivers": ["market_doc:tax_trade", "L9.industry.policy_change", "L9.macro.fx"], "score": -0.18}` |
| `L0.tech.ai_automation` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.45 | `{"components": {"classification": "ai_automation_demand_or_productivity", "direct_transmission_hits": ["A股", "产业链", "出口", "板块", "进口"], "market_doc_examples": 5, "same_sentence_evidence_count": 7, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["AI", "人工智能", "大模型", "算力"]}, "drivers": ["market_doc:ai_automation", "L9.media.report"], "score": 0.28}` |
| `L0.tech.breakthrough` | `fundamental_score` | `draft_known_market_doc_review_required` | `Known` | yes | 0.44 | `{"components": {"classification": "technology_breakthrough_or_commercialization", "direct_transmission_hits": ["A股", "产业链", "供应链", "出口", "板块", "沪深"], "market_doc_examples": 5, "same_sentence_evidence_count": 5, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["突破", "量产"]}, "drivers": ["market_doc:breakthrough", "L9.media.report", "L9.industry.compete_risk"], "score": 0.24}` |
| `L0.tech.substitute_tech` | `fundamental_score` | `unknown_market_doc_clean_evidence_required` | `Unknown` | yes | 0.0 | `{"blocked_reason": "market_doc_clean_substitution_risk_evidence_required", "clean_substitution_risk_examples": 0, "required_policy": "needs at least two same-sentence examples where an alternative technology displaces or threatens an A-share company, industry, board, or supply chain; exclude domestic import-substitution opportunity, foreign macro substitution, trade-law replacement, and broad non-A-share market commentary", "retained_market_doc_examples": 5, "review_required": true}` |
| `L8.shock.black_swan` | `risk_discount` | `draft_known_market_doc_review_required` | `Known` | yes | 0.48 | `{"components": {"classification": "geopolitical_or_black_swan_supply_risk", "direct_transmission_hits": ["供应链", "出口"], "market_doc_examples": 5, "same_sentence_evidence_count": 8, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["冲突", "战争", "袭击", "霍尔木兹"]}, "drivers": ["market_doc:black_swan", "L9.media.report"], "score": 0.55}` |
| `L8.shock.supply_break` | `risk_discount` | `draft_known_market_doc_review_required` | `Known` | yes | 0.47 | `{"components": {"classification": "supply_chain_or_input_disruption", "direct_transmission_hits": ["个股", "出口", "板块", "概念股", "进口"], "market_doc_examples": 5, "same_sentence_evidence_count": 7, "score_mapping": "bounded review-only score in [-1, 1]", "target_hits": ["供应中断", "停产", "断供"]}, "drivers": ["market_doc:supply_break", "L9.media.report"], "score": 0.45}` |

## Interpretation

- Market-document Known drafts are review-only score suggestions backed by retained local snippets.
- Ambiguous, noisy, or unprofiled packets stay Unknown instead of fabricating a score.
- Production score-affecting writes remain disabled.
