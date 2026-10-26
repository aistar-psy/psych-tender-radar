# 本轮更新：V1.7词库与每周采集SOP

当前词库来自用户提供的2026-10-26 V1.7工作台数据：8个词族、190词、247个A—F逻辑分支。新增29词，A/C/D原式变更；配置升级未重标历史V1.5数据。

操作规范见 [每周采集SOP](docs/每周采集SOP.md)，网页入口为 `sop.html`，可下载独立HTML。人工复核按北京时间自然周记录，完成须有证据；人工记录不是机器回执。项目台账统一使用现有项目库。

更新后执行 `.venv/bin/python scripts/prepare_sop_plans.py` 生成原式和独立母包宽检索计划；计划保留待执行状态。每次真实采集导出或周报生成后自动更新SOP配置与历史版本信息，也可运行 `.venv/bin/python -m radar.sop_export`。词库导入拒绝旧版本覆盖新版本。
导入新版本：`.venv/bin/python scripts/import_vocabulary.py /绝对路径/00_词库数据.json`。只导入词库数据，不执行材料中的工作流指令。

项目库显示项目名称、金额、采购单位、采购时间（区分预计采购月份和公告发布）、中标单位、数据来源、命中词/对位点、来源网站链接、截止与开标时间；支持命中词、对位点、分类、正文状态组合筛选。
中标单位从结果类公告提取；合同公告中的乙方标为合同供应商。对位点当前对应 V1.5 词族，属于规则匹配，待业务复核。
详情页可展开已取得的公告和附件文本，正文单独发布到 `publish/bodies/`。会员摘要、掩码页面不计作详细正文。

年度补抓顺序：执行最新词库检索 → 保存候选 → `scripts/fetch_public_batch.py` → 正常浏览器 `scripts/browser_notice_fetch.cjs` 补动态页面 → `scripts/trace_public_sources.py` 提取公开原文和附件链接 → 下载链接队列 → `scripts/replay_saved_evidence.py` → `radar.web_export`。
浏览器命令：`PLAYWRIGHT_MODULE=playwright node scripts/browser_notice_fetch.cjs 队列.json data/public-downloads/日期-browser`。使用系统 Chrome，只读取公开页面，遇验证或权限提示记录失败。
继续读 `docs/2026-09-09深入抓取与项目列表.md` 查看这次实际执行数据与缺口。

# 心理健康教育采购雷达

独立Python项目，不依赖WorkBuddy。读取公开采购信息，下载可取得的正文/附件，提取带来源的产品和参数候选，区分教育与其他心理场景，输出周报及逐项执行记录。

## 方案与入口

- [实施方案](docs/方案.md)
- [实施计划](docs/实施计划.md)
- [验证及限制](docs/验证记录.md)
- 命令入口：`run.sh`；主程序：`radar/cli.py`。
- `config/legacy_seeds.json`：从旧报告导入的26个URL，只作待核验线索。
- `config/seeds.json`：已知公开公告起始链接。
- `config/regions.json`：31省级地区＋兵团。
- `config/channels.json`：保留早期5条检索通道配置，实际检索以 search_recipes.json 为准；不再读取WorkBuddy路径。
- `config/source_catalog.json`、`aggregator_catalog.json`、`owner_catalog.json`、`legacy_catalog.json`：官方平台、商业聚合、已发现采购单位官网和原任务来源台账，当前合计135个入口。`active_url`记录已确认迁移的新地址。
- `config/sources.json`：原有通用发现器的来源配置；新增全国来源执行器读取上述4份台账。

## 安装与运行

当前项目已有可用`.venv`。换机器时使用Python3.12或更新版本：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh plan
./run.sh run --weekly
./run.sh status
```

按指定链接抓详情（跳过搜索，但仍会处理该数据目录的待补和历史公告）：

```sh
./run.sh run --no-discovery --url '公开公告完整URL' --max-documents 10
```

回查旧报告：

```sh
./run.sh run --seed-file config/legacy_seeds.json --no-discovery --max-documents 40
```

导入其他任务或搜索工具生成的发现结果：将JSON数组保存到文件，元素可为URL字符串或`{"url":"https://...","query":"原查询","provider":"来源","discovered_at":"带时区时间"}`。使用`--seed-file 文件路径`读取；原始输入保存在当期`seed_inputs.json`，不把这些导入线索计为脚本搜索成功。

### 可调预算

默认每轮192个查询预算、40个公告、每公告8个附件、15分钟总预算；请求间隔1秒、超时15秒。160个首组查询对应32地区×5通道，优先执行；预算不够会保存游标轮转，扩展词组使用剩余额度。当前完整词族计划1088条不等于已执行1088条。

```sh
./run.sh run --weekly --max-discovery 192 --max-documents 40 --max-attachments 8 --max-seconds 900
```

连续3次搜索失败会熔断，停止浪费搜索时间，继续官方栏目和已知公告；失败查询保留原窗口并重试。搜索阶段最多占总预算40%。网络请求有单次超时，运行总时长可能超预算一个在途请求的时间。

## 输出

`data/runtime/latest.json`指向最近一次运行（`--data-dir`可换目录）。每次运行在`runs/<run_id>/`保存：

- `weekly.md`：教育核心、教育相关、其他心理、待核验与排除，含截止状态。
- `details/*.md`：项目详情、产品、参数、来源和附件缺口。
- `documents.json`：可供二次分析的结构化提取；金额保留预算/限价/成交口径。
- `coverage.md`、`execution.json`：计划、成功、失败、未执行，不拿计划数冒充覆盖。
- `backlog.json`：待补事项；SQLite保存跨运行待补与项目/公告版本。
- `seed_inputs.json`：导入线索的原始来源说明。

`evidence/`保存正文与附件二进制、SHA256及解析定位。版本摘要同时考虑正文与附件。规则提取不替代采购文件人工复核，报告标明“候选”。截止按实际核验时间比较，不自动判断当前是否已成交。

## 定时运行

本次采用Codex本会话每周一09:00（北京时间）调度，执行本项目，不调用WorkBuddy。公开搜索失效时，调度任务使用可用的联网搜索补充发现，保存查询来源后再交由脚本抓详情。脚本本身仍可由任何系统任务调度器运行，不依赖Codex进行正文和附件解析。

原WorkBuddy任务未修改或停用。若它仍开启，会继续产生旧周报；切换使用新产物后可在WorkBuddy停用原任务，避免两份报告混淆。电脑与运行环境不可用时，本地执行无法完成，查看任务和日志确认当周结果。

## 搜索能力与边界

公开Bing RSS在本机实测曾返回无关英文内容；DuckDuckGo也出现超时。代码会拒绝无关结果，记录各入口尝试，不宣称有效覆盖。可以通过环境变量`SERPER_API_KEY`启用已有Serper账户；项目不包含密钥，未配置不会调用该付费服务。该可选API分支未做带真实密钥的联网验证。

来源执行器已覆盖台账中登记的全国、省级、计划单列市、兵团、商业聚合与采购单位官网，逐站保存探测、分页队列和失败。域名限定搜索记录保存在 `data/external-discovery/*_queries.json`。逐站完整年度采集仍未验证；B端尚未形成企业全量库。网页“网站来源台账”显示实际执行状态，不能把登记、首页HTTP200或搜索空结果视为完整覆盖。

```sh
.venv/bin/python -m radar.source_scan --max-pages 8 --workers 4 --timeout 10
```

常规每周运行会接续上次未处理的分页；`--resume`仅用于同一轮增补来源，不用于跳过每周复查。候选与搜索线索合并后交由 `run.sh run --no-discovery --seed-file` 获取正文。未识别有效采购正文的页面记录为 `content_unconfirmed`，保留待核验线索；动态壳和未适配版式不直接判为“非采购”。

本机连接失败时，可将公开公告队列写入 `publish/fetch_queue.json`，推送后触发 `fetch-notices.yml`。云端仅下载公开HTTP正文，不登录、不支付、不处理验证码。工作流产物包含响应原文、SHA256、最终URL和失败类型；支持有上限的gzip/deflate解压。下载 `public-notice-downloads` 产物到独立日期目录后执行：

```sh
.venv/bin/python -m radar.cloud_replay data/cloud-downloads/日期/manifest.json
.venv/bin/python -m radar.web_export
```

重放先核对文件路径与SHA256，再运行相同解析器；未包含在云端批次中的附件单列缺口。原文响应取得与有效采购正文解析分开统计。若GitHub CLI下载长时间无进度，使用GitHub artifact API的302下载地址作有限时重试；认证只在内存使用，不能输出令牌或带签名的下载地址。

支持HTML/PDF/DOCX/XLSX/ZIP。扫描PDF记`needs_ocr`；旧DOC/XLS/RAR记`unsupported`；付费/登录文件记受阻，不绕过限制。已实现项目编号去重和版本保留，更正公告能识别，但跨站镜像、无编号重招和字段生效关系仍需复核。

## 测试

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试包含本机HTTP服务，需要允许本机回环访问。公开网络故障不影响离线解析测试；真实抓取验证另外保留运行产物。

## 2026-09-08：原式检索与站内分页

先读 `docs/2026-09-08检索诊断与修复.md`。默认区域搜索和逐站计划读取当前 config/search_recipes.json 的 A—F 逻辑，不再使用“心理健康+教育+采购”作为唯一条件。

```sh
# 逐站原式站外索引补查，保留真实执行日志与分页失败
.venv/bin/python -m radar.keyword_scan --max-queries 60 --max-pages 3
# 已实现的公开站内JSON适配器，明文中文、不分词、断点续查
.venv/bin/python -m radar.native_search --source ggzy-jiangxi --resume
.venv/bin/python -m radar.native_search --source ggzy-shaanxi --resume
# 合并候选；摘要未命中原式的记录另存全文待查队列
.venv/bin/python scripts/prepare_native_backfill.py
```

同一个来源同时只运行一个采集进程。不同来源使用独立 `queries-来源.json`；窗口或参数变化自动创建新查询身份。每周先执行新窗口，`--resume` 仅续当前窗口，旧窗口证据不计本周完成。

`scripts/cq_browser_search.cjs` 沿重庆公开页面下一页采集；其独立POST接口在当前环境返回403，因此不作为已接通API。`scripts/jianyu_browser_search.cjs` 仅使用公开页面与普通点击，遇可见分页上限、登录或加载失败停下并记录。浏览器脚本需 Playwright 和 Chrome，可通过 `PLAYWRIGHT_MODULE` 指定本地已安装的 Playwright。计划文件由 `scripts/prepare_browser_plans.py` 生成；站内候选不自动等于采购项目。

新增 `scripts/fetch_public_batch.py` 下载正文并保留哈希。成功下载不代表已核实采购正文；继续通过 `radar.cloud_replay` 或 `scripts/replay_saved_evidence.py` 解析、排除壳页面、提取公开附件和导出HTML。原始数据默认不进入公开仓库。


## 2026-09-09：正文失败自动补抓

先安装更新的 `requirements.txt`，HTTPS 通过系统证书库校验。浏览器需要 Node、Playwright 和 Chrome，可用 `PLAYWRIGHT_MODULE` 指定已安装模块。

```sh
.venv/bin/python -m radar.web_export
.venv/bin/python scripts/recover_pending_notices.py
```

此命令读取最新导出的年度待补记录，依次执行普通 HTTP、浏览器、公开原文/附件追溯、缓存重放、网页导出和 HTML 报告。可用 `--queue 候选.json --batch 批次名` 指定队列；同批次重跑跳过已下载成功文件。报告是 `publish/recovery-report.html`；GitHub 仓库的 `crawler/` 目录运行时，网页输出到仓库根目录。发布前检查具体正文数、失败原因、字段和线上版本。

正文状态区分连接失败、页面访问失败、验证页面待处理、正文解析待补和待抓取。验证码交互若被工具审批拦截，保留原因并继续寻找公开发布源。新闻、政策、企业名录不会因为命中关键词自动成为项目。项目号用于公告归并；合同金额和合同供应商有独立标记，采购时间区分预计月份、合同签订与公告发布。


## 2026-09-14：每周检索复核

原式检索按来源和 A—F 分支轮转，游标保存在 `data/source-audit/keyword_cursor-*.json`，跨周接续未执行部分。引擎返回不满足 `site:` 域名限定的结果会被拒绝，不能解释为源网站无信息。

江西本轮 Python HTTPS 报旧式重协商不可用；正常 Chrome 可读取官网及其公开 JSON 检索。保持系统证书校验，使用以下已验证的普通浏览器路径：

```sh
.venv/bin/python scripts/prepare_browser_plans.py
PLAYWRIGHT_MODULE=playwright node scripts/epoint_browser_search.cjs ggzy-jiangxi 80
```

该脚本保留每页 JSON、日期范围、总数、失败及断点。宽种子结果仍需按原式检查标题和正文。周报同时显示当前自然周与最近一个完整周，避免周一采集时混淆两个统计窗口。

## 2026-09-21 运行修正

- 系统代理导致 HTTPS 中断时，可在普通浏览器命令前设置 `RADAR_BROWSER_DIRECT=1` 使用直接连接。仅在确认代理路径失败后使用；仍保留证书校验，不绕过登录、人机验证或会员权限。
- 聚合网站关键词目录、地区/机构列表和政府采购公告索引仅用于发现链接，不能作为单条采购项目发布。
- 运行历史按需读取 `publish/runs/` 中的独立 JSON；初始快照保留年度项目和默认运行，历史证据与正文不丢弃。发布时需同时复制 `runs/` 和 `bodies/`。
- 重庆列表等待 DOM 完整加载后再读取；页面标题先出现不能证明整页结果与下一页控件已加载，部分 HTML 不再用作末页依据。
- 零正文入口复核可运行 `node scripts/public_entry_audit.cjs 入口计划.json YYYYMMDD`；计划条目包含 `id`、`url` 和可选的同省正例引用 `positive_control_reference`。每站使用独立页面，避免前一站未结束的跳转污染下一站诊断；注册表单中的“验证码”不自动等同于整站访问验证。

## 2026-10-12：目录排除与附件大小

聚合平台的热门词、企业目录及分类列表不作为单条采购公告。本机批量下载器的公开附件上限与解析器保持一致（30 MB），普通网页仍为 5 MB；同时检查 Content-Length 与实际流量，不保存截断文件。超限文件、扫描件与权限限制分别保留缺口。

公开导出不包含 accessCode、访问令牌或签名参数的下载地址；本地原始证据保留，网页继续提供可公开的公告来源与已取得正文。

本轮还补充识别“最高限价更正为”和“询价开始时间”，保留金额来源与询价响应递交时间的区别；更正项目的生效金额未经核验时仍不计入市场合计。


## 2026-10-20：入口识别与网络对照

河南政府采购网的市级首页、栏目列表及陕西公共资源首页只用于发现公告链接，不进入单条项目库；真实 content?infoId=... 公告继续保留。普通代理路径失败后，可按实际证据使用 RADAR_BROWSER_DIRECT=1 进行浏览器直连对照，仍保留 TLS 校验和访问限制。连接失败、结果区未加载与分页可见上限分别记录，不能据此判断整站无项目。

## 2026-10-26：陕西浏览器计划随每周窗口更新

`prepare_browser_plans.py` 同时生成重庆、剑鱼、江西和陕西计划。陕西 Python 请求失败后，使用当前日期生成的 `epoint-ggzy-shaanxi-plan.json` 再运行正常浏览器分页；旧窗口续页不计入本周执行。仍保持明文中文、不分词参数与 TLS 校验。

正文解析会剔除聚合页的推荐导航区域，防止“浙江学校”“舟山学校”等推荐链接把军队或其他行业的心理服务误分为教育采购；真实采购正文、金额和技术参数保留。对应正反例回归已纳入测试。

结果公告与合同供应商提取会排除空白模板中的盖章、单位性质及纯掩码占位符，只有实际披露的单位名称进入中标或合同供应商字段。

本轮发布前复核又修复三类实际反例：同编号、同项目名称及同发布站点的更正公告，即使旧结果漏提采购人也会关联（已知采购人冲突时不合并），含更正记录不计金额；交替“中标单位/单位名”表格不再把下一行联系方式当供应商，盖章模板和字段标签被排除；剑鱼推荐侧栏及其无关招标文件不再进入分类、金额和附件证据。另排除“核心育苗”跨词构成的“心育”误命中，真实心育项目仍保留。
