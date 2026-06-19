# A-share event Unknown strict source gate

- Generated: `2026-06-19T17:45:44+08:00`
- Rows: `2`
- Market HTML files scanned: `14956`
- Strict candidates: `11`
- Strict review candidates: `8`
- Rows with strict review candidates: `2`
- Rows without strict source candidate: `0`
- Classifier-ready rows: `0`
- Known-draft sufficient: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## Rows

| dp_id | status | strict candidates | strict review candidates | required next evidence |
|---|---|---:|---:|---|
| L0.compete.new_entrant | strict_review_candidates_found | 1 | 1 | external entrant or cross-industry player, not incumbent expansion, same sentence/paragraph direct A-share company, sector, supply-chain, or margin/share pressure transmission, reviewed direction and bounded magnitude |
| L0.tech.substitute_tech | strict_review_candidates_found | 10 | 7 | negative substitute technology risk, not import-substitution opportunity, direct A-share company, sector, board, supply-chain, or margin/share pressure transmission, at least two clean examples or one high-conviction primary-source example |

## Interpretation

- Strict source candidates are still classifier inputs, not Known values.
- A row remains Unknown unless strict source evidence is reviewed, direction/magnitude are bounded, and approval records are created.
- This audit creates no runtime writes and does not mutate final scores.
