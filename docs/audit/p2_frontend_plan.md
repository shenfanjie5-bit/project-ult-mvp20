# P2 前端"加股票 + 系统启停" — 计划与恢复状态

> 压缩前存盘，便于压缩后恢复。分支 `feature/a-share-fixes`。

## 已完成（已 commit）
- `be5a313` C0：cninfo 年报抓取 + 章节抽取硬化（`scripts/fetch_annual_report.py` / `ingest_annual_report.py`）。
- `c5765bd` C1：schema 加固闭环填充 9 只 AI_COMPUTE A 股（`codex_prompt_gen.py` inline DP_SCHEMA + Optionality 拆分；drift 41→0；compile 干净；已打分）。000977 保留 xhigh pilot。
- `bfc704a` P1：加股票**后端**（`mvp20/onboard.py` + `config/tushare_industry_map.yaml` + `mvp20/server.py` 端点 + `mvp20/derive.py` 单只过滤 + `tests/test_onboard.py`）。
- 全量测试绿。茅台 onboard 测试残留已清。

## 后端端点（P2 前端要接的，已就绪 + 实测通过）
- `POST /api/project-ult/recognize`  body `{market:"A|HK|US", code}` → `{ok, ts_code, name, suggested_industry_id, candidate_industry_ids, all_industry_ids, already_in_pool}`
- `POST /api/project-ult/onboard`  body `{ts_code, name, industry_id, do_codex?}` → `202 {job_id, steps[10]}`（守卫：bad ts_code/industry→400，已在池→409）
- `GET  /api/project-ult/onboard?job_id=X` → `{status: pending|running|ready_preliminary|ready_full|error, step, step_idx, preliminary, full}`
- `GET  /api/project-ult/industries` → `{industries:[{industry_id,name,status}]}`（12 个 active）
- 安全：仅这 2 个 POST 白名单；其余 POST 仍 405（只读保持）。
- 后端启动：`python -m mvp20.cli serve --host 127.0.0.1 --port 8701 --cors-origin http://127.0.0.1:1420`
- onboard 步骤（进度条 10 步）：`mvp20/onboard.py::ONBOARD_STEPS` = universe, generate_overlays, collect, annual_report, derive, compile, score_preliminary, codex_fill, recompile, rescore。

## 前端结构（FrontEnd/，React18+Vite+Tauri+TanStack Query）
- `src/App.tsx`（路由/侧边栏）、`src/pages/`（DailyReport/Admin/Subsystems/ProjectUltGraph）、`src/components/layout/StatusBar.tsx`（底部状态栏，"mvp20 BFF unavailable" 在此）。
- `src/api/client.ts`：`apiClient.get/post`，解 `{data,request_id}` 信封；`src/utils/dataMode.ts`：`VITE_DATA_MODE=projectUlt` 走真实后端，Vite 代理 `/api`→:8701（`FrontEnd/.env.local` 已配好）。
- 起前端：`.claude/launch.json` 已配 `npm --prefix FrontEnd run dev`（:1420）；或 Preview MCP `preview_start "frontend"`。
- ⚠️ 项目在 `~/Desktop` 下，受 macOS TCC——若 Claude.app 没 Full Disk Access，后端读不了文件（500 / Operation not permitted）。需给 Claude.app 开 FDA 并重启。

## P2a — 加股票 UI（纯 React，先做，浏览器可测）
入口（按钮/弹窗，放工作台或侧边栏）→ 市场下拉(A/HK/US) + 代码框 → "识别"(`/recognize`，显示名称+行业下拉默认=建议值可改) → "加入并分析"(`/onboard`→job_id) → 进度条(轮询 `/onboard?job_id=`，10 步；`ready_preliminary` 先展示初步分，`ready_full` 自动刷新) → 跳该股分析页。用 TanStack Query mutation + 轮询。

## P2b — 系统启停控制（已完成 2026-06-03，磁盘上；全部 gitignored）
新增/改动（均 gitignored）：
- `src-tauri/src/lib.rs`（重写）：3 个 `#[tauri::command]` —— `start_system(source,interval)`/`stop_system()`/`system_status()`；`SystemState{serve,collector: Mutex<Option<Child>>}` 经 `.manage()` 托管；`find_repo_root()` 从 cwd 上溯找 `.venv/bin/python`+`mvp20`；spawn `.venv/bin/python -m mvp20.cli serve …` + `… scripts/collector.py --source <S> --interval <N>`（cwd=repo root）；stop=`child.kill()`+`wait()`（collector 每 tick 原子提交，SIGKILL 安全）；status 用 `try_wait()` 判活并回收。无新依赖（serde 已在）。
- `src-tauri/capabilities/default.json`（NEW）：main 窗口授 `core:default`（自定义命令本身 v2 无需 ACL）。
- `src/api/hooks/useSystemControl.ts`（NEW）：`useSystemStatus`(3s 轮询)/`useStartSystem`/`useStopSystem`，全部 `isTauriEnvironment()` 门控。
- `src/components/layout/SystemControl.tsx`（NEW）：footer 紧凑控件——状态灯+「系统 运行中/已停止」+ 源下拉(tushare/akshare/mock)+间隔输入(默认600s)+启动/停止按钮；浏览器返回 null。
- `src/components/layout/StatusBar.tsx`：左簇挂 `<SystemControl/>`。

验证：
- `cargo build` 增量 13.79s 干净通过（命令注册 + generate_handler/generate_context 宏 + capabilities 解析 + Serialize + 借用检查）。
- `npm run tauri dev`：vite ready(1420) → `Finished dev in 0.29s` → `Running target/debug/ai_research_frontend`（**窗口启动成功、webview 加载**；随后 `ECONNREFUSED 8701` 是预期——系统未启动）。无 Rust panic。
- spawn 目标独立验证：serve 早已实测；collector `--source mock --interval 1 --max-cycles 2 --hot-db /tmp/...`（临时库、328 只 upsert 1312/轮、干净退出、已删）。合法源含 mock/tushare/akshare。
- tsc + eslint 全绿（4 文件）。
- **唯一未自动化**：桌面 WebKit 窗口里点「启动/停止」按钮——Preview MCP 驱动的是 Chrome，碰不到 WebKit 窗口，需在桌面 app 手点。

待办/已知小瑕疵：
- do_codex=false 时进度条把第 7-10 步(codex/recompile/rescore)也显绿勾（实际跳过）——终态 step_idx=10 所致，纯视觉，建议给跳过步加 "skipped" 态。
- onboard 的 generate-overlays 步会"重写"已有 overlay。**已核查(B)：merge-preserve 正确，codex 填充(Known/N/A/Optionality 52 值)字节级保留、零丢失**；变化仅 (a) YAML 重新序列化(格式噪音，致 git 显 modified) + (b) 9 个事件驱动 Inactive→Unknown(设计内刷新)。低优先小瑕疵：onboard 只重 derive 新股，故已有股的事件节点刷 Unknown 后短暂不回填(系统跑 derive 循环时自愈)；可选修：onboard 把 generate-overlays 限定到新股 + 把已提交 overlay 规范化为 canonical 格式消除噪音。
- 停止用 SIGKILL；如需优雅可加 libc SIGTERM-then-kill。
- **孤儿进程缺口**：若系统运行中直接关闭 app，spawn 的 serve+collector 子进程不会被自动杀（std Child 无 kill-on-drop）→ 残留占 8701/继续采集。建议在 Builder 的 on_window_event/Drop 或退出钩子里 stop_system，或用进程组 kill。（本次未触发：关窗前未点启动。）

## P2a — 已完成（2026-06-03，磁盘上；FrontEnd/ 被 .gitignore，不进主仓库 commit）
新增/改动（均在 `FrontEnd/`，gitignored）：
- `src/api/hooks/useOnboard.ts`（NEW）：`useRecognize`/`useStartOnboard`（mutation）+ `useOnboardJob`（轮询 query，1.5s，终态停轮询）+ 类型 + `isTerminalStatus`。
- `src/pages/AddStock/index.tsx`（NEW）：完整状态机——市场下拉(A/HK/US)+代码输入→识别(显示名称/行业，行业下拉默认=后端建议，suggested=null 回退首项)→CodeX 开关+加入并分析→10 步进度条+步骤列表(done/active/error/pending)+初步评分卡(running 时显示"CodeX 填充中")+完整评分卡(full 到位)+查看个股详情。支持 `?job_id=` 续看(惰性 useState 读 URL，刷新不丢)。
- `src/App.tsx`：lazy 路由 `/add-stock`。
- `src/utils/constants.ts`：Sidebar core 组新增"添加股票"(PlusCircle, alwaysUnlocked)。

后端配套修复（**可进 commit**，`mvp20/onboard.py` + `tests/test_onboard.py`）：
- 修 worker 死变量 bug：`prog` 算了 `status="ready_preliminary"` 却硬编码 "running"；且 `preliminary_json` 只在最后写 → "先展示初步分"无法实现。
- 改：`run_onboard` 加 `on_preliminary` 回调，初步分一算出即持久化(status 仍 running)；前端按 `preliminary`/`full` 字段**存在性**渲染(不依赖 status 串)。终态：do_codex=True→ready_full；False→ready_preliminary。
- 加 2 个 hermetic 测试(Event 同步，非 sleep)：初步分 running 中途可见→full 终态；do_codex=False→ready_preliminary 终态无 full。

验证(真实后端 :8701 + Vite 代理 :1420)：
- recognize 200(经代理)：000977→浪潮信息/IT设备/AI_COMPUTE/已在池；600519→贵州茅台/白酒(未映射→suggested=null,回退首项)；abc→ok=false reason；HK 00700→腾讯/format-only/已在池。onboard 000977→409。
- 进度+评分渲染：注入合成 onboard_jobs 行(999999.SZ, running, step_idx=7, 有初步分无 full)→前端经真实 GET 端点轮询→进度条 70%、步骤 1-6 绿勾+codex_fill 转圈、初步评分卡(WATCH/-0.181/-0.177/-0.139/主因路径)+"CodeX 填充中"、无 full 卡、无详情按钮。验毕删除合成行(零残留：未碰 universe/overlay/其它表)。
- tsc + eslint 全绿（4 文件）；后端全量 pytest 待确认。

## P2b 可用性收尾（A）— 已完成 2026-06-03（磁盘上，gitignored）
针对"打开 app→子页面全报错"的体验问题：
- **A1 启动门面**（`src/components/layout/SystemGate.tsx` NEW + `useBackendReachable` in `useSystemControl.ts` + App.tsx 包裹路由）：projectUlt 模式探 `/api/health`，后端不通时**主区显一个"系统未启动"门面**(Tauri 显源/间隔/启动按钮；浏览器显手动命令)，不再让每页各自报错；后端起来后 4s 轮询**自动开门**。**浏览器实测通过**：down→门面、up→自动进工作台。
- **A3 关 app 杀子进程**（`src-tauri/src/lib.rs`）：`run()` 改 build+run，拦 `RunEvent::ExitRequested|Exit` → `kill_all`，关窗即杀 serve+collector，**修掉孤儿缺口**。cargo build 2.98s 通过。
- **A4 进度条 skipped 态**（`AddStock/index.tsx`）：do_codex=false(ready_preliminary) 时第 8-10 步显「（跳过）」而非绿勾。**实测通过**(注入合成 job 验证)。
- A2(控件提到顶部)：由 A1 门面(停止态醒目)+footer SystemControl(运行态)覆盖，未单列。
- tsc+eslint 全绿；前述 3 个已知瑕疵中 **error-wall / 孤儿 / skipped 三项已修**；仅"SIGKILL 非优雅"留作可选。

## 恢复后下一步
1. ~~P2a~~ ✅ 完成（含真实 600519 onboard 端到端实测 + 还原）。
2. ~~P2b~~ ✅ 实现+编译+启动验证；桌面「启动/停止」按钮手点仍需你在 Tauri 窗口验。
3. ~~B 数据完整性~~ ✅ 核查完毕：merge-preserve 不丢填充（52 值字节级保留），非 corruption。
4. ~~A P2b 可用性~~ ✅ 完成（门面/杀子进程/skipped）。
5. C（A股遗留）：hermetic 修 `test_list_only_company_with_tier_filter`(已 spawn 任务) + 000977 beat_probability stale-evidence。
6. 提交范围：`mvp20/onboard.py`+`tests/test_onboard.py` 已提交 (e3bede2)；前端/Tauri 全 gitignored 不进 git；本 doc 未提交。

## 多 agent 审查 + 修复（2026-06-03）
6 reviewer + 对抗式核验 workflow → raised 31 / confirmed 27 / rejected 4；去重 17 唯一问题。
3 个并行 fix agent(文件不重叠)实现,**我独立验证**(非采信自报):full suite 1031 passed/0 failed、H1 实证 scoped-generate 只动目标股、前端 tsc+eslint+cargo 全绿。
- High 已修:**H1**(generate-overlays 加 `--only-ts-code`,onboard 不再全量重写→止住跨股 coverage 漂移)、**H2**(onboard 并发上限2 + 409/429)、**H3**(Tauri check-and-spawn 持单锁 + start_lock + 删 footer 重复启动按钮)。
- Medium 已修:M1/M2(universe `os.replace` 原子写 + `_ONBOARD_PIPELINE_LOCK` 串行)、M4(score 含 error→status=error)、M5(compile snapshot 校验+改正注释)、M6(refetchInterval error 短路)、M7(SystemGate 连续2失败才坍缩)、M8(StepList 由后端 steps 驱动)。
- Low/Nit 已修:L1 sort、L2 HK/US 缓存、L3 CORS+POST、L4 name≤128、L6 回滚、L7 PROJECT_ULT_ROOT、N1/N2/N3。
- **暂缓**:L8(tauri.conf CSP)——无法验证 WebKit、不盲改。
后端 6 文件(`onboard.py`/`server.py`/`cli.py`/`overlays.py`/`tushare_industry_map.yaml`/`test_onboard.py`)可提交;前端/Tauri 修复在磁盘 gitignored。
