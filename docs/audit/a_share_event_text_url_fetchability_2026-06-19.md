# A-share event-text URL fetchability

- Generated: `2026-06-19T09:07:56+08:00`
- Unique URLs: `8`
- Fetch success: `8`
- Primary text available URLs: `8`
- Body packets: `12`
- Body target-hit packets: `3`
- Body direct-transmission-hit packets: `0`
- Body signal sufficient for classifier: `0`
- Known candidates allowed: `0`
- Production writes allowed: `0`
- Score mutation: `none; this audit is read-only and does not alter realtime_current`

## URL Fetches

| title | status | primary chars | url |
|---|---:|---:|---|
| 黎巴嫩总统：本轮冲突致黎近18%国土受损 | 200 | 287 | https://api3.cls.cn/share/article/2404176?os=web&sv=8.7.9&app=CailianpressWeb |
| 俄外交部：俄将对欧盟新一轮制裁采取强硬反制 | 200 | 289 | https://api3.cls.cn/share/article/2404177?os=web&sv=8.7.9&app=CailianpressWeb |
| 霍尔木兹海峡开始有大型商船通行 | 200 | 242 | https://api3.cls.cn/share/article/2404182?os=web&sv=8.7.9&app=CailianpressWeb |
| 消息人士：因以军持续袭击黎巴嫩 伊朗推迟赴瑞士行程 | 200 | 255 | https://api3.cls.cn/share/article/2404183?os=web&sv=8.7.9&app=CailianpressWeb |
| 俄方称扎波罗热核电站连遭日均50次以上袭击 | 200 | 283 | https://api3.cls.cn/share/article/2404184?os=web&sv=8.7.9&app=CailianpressWeb |
| 瑞士4-1十人波黑 | 200 | 206 | https://api3.cls.cn/share/article/2404185?os=web&sv=8.7.9&app=CailianpressWeb |
| 财联社6月19日电，富时中国A50指数期货夜盘收跌0.23%。 | 200 | 47 | https://api3.cls.cn/share/article/2404186?os=web&sv=8.7.9&app=CailianpressWeb |
| 纽约时报广场发生枪击 | 200 | 146 | https://api3.cls.cn/share/article/2404188?os=web&sv=8.7.9&app=CailianpressWeb |

## Rows

| dp_id | target | body status | urls ok | target hits | direct hits | classifier-ready |
|---|---|---|---:|---:|---:|---:|
| `L0.compete.new_entrant` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.compete.price_war` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.compete.share_concentration` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.policy.access_license` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.policy.regulation` | `fundamental_score` | `body_available_but_insufficient` | 6 | 1 | 0 | no |
| `L0.policy.subsidy` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.policy.tax_trade` | `fundamental_score` | `body_available_but_insufficient` | 1 | 1 | 0 | no |
| `L0.tech.ai_automation` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.tech.breakthrough` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L0.tech.substitute_tech` | `fundamental_score` | `body_available_but_insufficient` | 6 | 0 | 0 | no |
| `L8.shock.black_swan` | `risk_discount` | `body_available_but_insufficient` | 8 | 7 | 0 | no |
| `L8.shock.supply_break` | `risk_discount` | `body_available_but_insufficient` | 6 | 0 | 0 | no |

## Interpretation

- Fetchability and body text are evidence inputs only.
- Body-level target hits still need direct A-share/industry/entity/supply-chain/trade transmission before classifier promotion.
- This audit emits no Known candidates and performs no runtime writes.
