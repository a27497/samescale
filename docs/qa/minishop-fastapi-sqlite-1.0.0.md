# MiniShop FastAPI / SQLite 1.0.0 资格与回归摘要

本报告只公开契约索引、检查名称、摘要、耗时和计数；完整原文、适配声明、参考实现、隐藏检查和资格工作区均留在批准的 Git 外私有目录。本次为交付后审计资格，不是预注册盲测，尚无被测快照验收结论。

## 固定身份

| 项目 | 值 |
| --- | --- |
| task_reference | `minishop-fastapi-sqlite@1.0.0` |
| requirement_sha256 | `sha256:31c93f958b80472ada981cc30f210d41d313bc23a7d27acc2ad4fd15f3070bdc` |
| baseline_adapter_sha256 | `sha256:3bbbf6e5ae731b7af577ff765b488d31a2fbb2e1fb42ce576b33e9af3e783f85` |
| oracle_adapter_sha256 | `sha256:1d07ebd38a6119f2e03a7c25ef27b1bfeba94d31f651491278512e2cb376ec46` |
| task_digest | `sha256:95f1b9baa8baee78753f53ec3882598d741f1c0efc8ffbdfc47831c8f0ffdadc` |
| verifier_digest | `sha256:cf3803e8cbad714e53ed1745d8336c3f5a2a0d3627e9445fa4d9e6805214bf30` |
| qualification_identity | `sha256:47c9b4b10d12ab90fce357a5754727013c257a77f33cbdf42fc1e5f1b8da1af8` |
| image_id | `sha256:e8e919870821cd896510b4f29e073b37ac7a5b711f7edeea508606a2defb84a3` |
| eligible_for_planning | `True` |

fetch 后 `main=1432cb94fc22e110e49e733bab7b96dc7d360a09`；分支 `codex/minishop-fastapi-sqlite-1.0.0-audit`。原有脏工作区未修改；本阶段未读取、复制或运行 DeepSeek MiniShop 快照、源码、自测或自报。被测接口声明 NOT_WRITTEN，3b NOT_AUTHORIZED_NOT_RUN。

完整包 19 文件 / 61,982 字节；baseline 工作区 7 文件 / 6,551 字节，oracle 覆盖后工作区 7 文件 / 9,781 字节。R 是 UTF-8 原始字节，5,184 字节，无末尾换行；未增删原文字符。两份适配声明和 R 的摘要均计入任务 manifest metadata 和整个包的 task_digest。

## 资格、缺陷控制与逐项结果

三次 baseline 均正常启动、正常 SUBJECT_RESULT、6/26 通过（20 项业务失败）；三次 oracle 均 26/26 通过。两组各自逐项布尔向量一致，退出码均 0；无基础设施失败、超时、截断或清理失败。实际构造并导入最终独立 CUSTOM 资格后，TaskStore 再次 inspect 返回 eligible_for_planning=true、reason_codes=[]。

| 运行 | 分类 | 通过/检查数 | 整次秒数 |
| --- | --- | ---: | ---: |
| accepted-baseline-1 | SUBJECT_RESULT / FAIL | 6/26 | 10.179923 |
| accepted-baseline-2 | SUBJECT_RESULT / FAIL | 6/26 | 10.095239 |
| accepted-baseline-3 | SUBJECT_RESULT / FAIL | 6/26 | 10.040321 |
| accepted-oracle-1 | SUBJECT_RESULT / PASS | 26/26 | 12.044928 |
| accepted-oracle-2 | SUBJECT_RESULT / PASS | 26/26 | 11.716972 |
| accepted-oracle-3 | SUBJECT_RESULT / PASS | 26/26 | 11.841092 |
| accepted-control-price | SUBJECT_RESULT / FAIL | 25/26 | 11.924872 |
| accepted-control-partial | SUBJECT_RESULT / FAIL | 25/26 | 11.934051 |
| accepted-control-retry | SUBJECT_RESULT / FAIL | 24/26 | 11.844434 |
| accepted-compat-metadata | SUBJECT_RESULT / PASS | 26/26 | 11.856999 |

三个缺陷控制均从已通过的 oracle 副本开始，各只修改一个唯一代码位置，接口声明、隐藏检查和固定镜像不变。控制类型分别为信任客户端金额、库存提交早于订单插入、同键重试再次扣库存。它们分别命中 C05、C17、C18/C20，均为正常业务 FAIL。有限控制样本只证明能检出这些注入的缺陷，不证明总体覆盖率。

逐项名称及条款依据见[契约映射](../MINISHOP_FASTAPI_SQLITE.md#检查项与-r-的具体映射)。下表 B/O 的三个字符分别对应三次最终正式重复，P 为通过、F 为业务失败。

| 检查项名称 | baseline 1/2/3 | oracle 1/2/3 | 价格控制 | 部分提交控制 | 重扣库存控制 |
| --- | --- | --- | --- | --- | --- |
| C01_catalog_fields_and_minimum | P/P/P | P/P/P | P | P | P |
| C02_sqlite_integer_prices | P/P/P | P/P/P | P | P | P |
| C03_catalog_database_authority | P/P/P | P/P/P | P | P | P |
| C04_create_and_query_order | F/F/F | P/P/P | P | P | P |
| C05_server_repricing_ignores_amounts | F/F/F | P/P/P | F | P | P |
| C06_sqlite_order_and_line_persistence | F/F/F | P/P/P | P | P | P |
| C07_stock_decrement | F/F/F | P/P/P | P | P | P |
| C08_insufficient_stock_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C09_unknown_product_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C10_zero_quantity_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C11_negative_quantity_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C12_fractional_quantity_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C13_boolean_quantity_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C14_null_quantity_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C15_missing_quantity_rejected_unchanged | F/F/F | P/P/P | P | P | P |
| C16_multiline_failure_rolls_back | F/F/F | P/P/P | P | P | P |
| C17_injected_database_failure_rolls_back | F/F/F | P/P/P | P | F | P |
| C18_same_key_retry_returns_original | F/F/F | P/P/P | P | P | F |
| C19_same_key_changed_content_conflict | F/F/F | P/P/P | P | P | P |
| C20_concurrent_same_key_single_order | F/F/F | P/P/P | P | P | F |
| C21_concurrent_orders_do_not_oversell | F/F/F | P/P/P | P | P | P |
| C22_restart_preserves_order_and_stock | F/F/F | P/P/P | P | P | P |
| C23_frontend_html_loads | P/P/P | P/P/P | P | P | P |
| C24_frontend_local_resources_load | P/P/P | P/P/P | P | P | P |
| C25_page_and_api_http_scenario | F/F/F | P/P/P | P | P | P |
| C26_local_start_and_test_documentation | P/P/P | P/P/P | P | P | P |

另有一个正确兼容副本 26/26 PASS：仅改变接口包装/响应元数据、相对数据库路径、初始化库存和业务无关的启动记录，并在并发时暂时拒绝请求；核心订单业务仍来自独立 oracle。同一次检查内的业务协议追索实际发生 C20=1 次、C21=2 次，均收敛且未重复扣库存；这些 HTTP 请求不是重新运行 Verifier。它验证适配及语义比较，不是缺陷样本、被测声明或 DeepSeek 结果。重启从冻结源码重新物化，只迁移 SQLite，运行目录内生成的旁路文件不参与恢复。

开发准备和所有原始观察完整保留：最初准备 3 次，五个被替代版本分别 9、9、9、10、10 次，最终版本 10 次，总计 60 次物理任务 Verifier。被替代版本用于修正静态 API 字符串推断、文档关键词限制、初始库存依赖及完整 JSON/运行目录比较、并发必须立即全部 2xx 等 R 未固定的条件；没有自动重试或删除失败观察来挑选结果。各版本独立保管，旧资格不用于最终准入。原资格元数据的物化目录定位也已修正，重新核对实际非空工作区、摘要及隐藏材料隔离；原元数据留档。

表中只有最终 task_digest 的六次资格、三次单点缺陷控制及一次正确兼容对照；前 50 次不混入最终重复证据。全部 60 次整次均 ≤25 秒；最初三次为 10.056985、11.992685、9.864582 秒，其余被替代版本的逐次计数/耗时见公开 JSON 的 superseded_revision、superseded_revision_2、superseded_revision_3、superseded_revision_4、superseded_revision_5。最终准入使用独立 accepted-managed-store 和 final-task-policy.json，FINAL_ADMISSION.json 指向已核对的最终文件。

## 不重叠的分段耗时

整次从加载任务/准备独立工作区开始，包含容器预检、执行、清理、结果保存和私有权限恢复。下表各行五段之和等于整次；计时舍入误差小于 0.002 秒。

| 运行 | 镜像预检/创建 | 挂载/隔离检查 | start --attach | 容器清理 | 准备/保存/其余 | 整次 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| accepted-baseline-1 | 0.273000 | 0.059000 | 9.665000 | 0.120000 | 0.062923 | 10.179923 |
| accepted-baseline-2 | 0.272000 | 0.049000 | 9.592000 | 0.112000 | 0.070239 | 10.095239 |
| accepted-baseline-3 | 0.245000 | 0.042000 | 9.547000 | 0.145000 | 0.061321 | 10.040321 |
| accepted-oracle-1 | 0.267000 | 0.044000 | 11.556000 | 0.109000 | 0.068928 | 12.044928 |
| accepted-oracle-2 | 0.283000 | 0.047000 | 11.206000 | 0.111000 | 0.069972 | 11.716972 |
| accepted-oracle-3 | 0.260000 | 0.047000 | 11.340000 | 0.121000 | 0.073092 | 11.841092 |
| accepted-control-price | 0.280000 | 0.047000 | 11.371000 | 0.145000 | 0.081872 | 11.924872 |
| accepted-control-partial | 0.293000 | 0.051000 | 11.400000 | 0.117000 | 0.073051 | 11.934051 |
| accepted-control-retry | 0.263000 | 0.047000 | 11.340000 | 0.120000 | 0.074434 | 11.844434 |
| accepted-compat-metadata | 0.268000 | 0.047000 | 11.345000 | 0.121000 | 0.075999 | 11.856999 |

`SANDBOX_START`、`PROCESS_START`、`PROCESS_WAIT` 记录同一次附加执行的重叠阶段；上表只取 SANDBOX_START，其他重叠时长不相加。start --attach 包括容器启动、整个 Verifier 主体及附加流返回，不能称为纯启动耗时。

Verifier 主体另用单调时钟记录服务启动、业务检查、服务停止和其余四段；均为主体内部的互斥区间，不与上一表叠加。检查段扣除了内部重启所占的服务启动/停止时间。下面服务启动/停止包含重启涉及的进程，具体次数不是 API 成功计数。

| 运行 | 服务启动 | 业务检查 | 服务停止 | 其余 | 主体合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| accepted-baseline-1 | 2.336360 | 6.193057 | 0.428120 | 0.272412 | 9.229949 |
| accepted-baseline-2 | 2.380333 | 6.039600 | 0.428321 | 0.280875 | 9.129130 |
| accepted-baseline-3 | 2.302136 | 6.129289 | 0.377925 | 0.340641 | 9.149992 |
| accepted-oracle-1 | 2.508658 | 8.020901 | 0.377987 | 0.255800 | 11.163347 |
| accepted-oracle-2 | 2.499187 | 7.656742 | 0.377960 | 0.257905 | 10.791794 |
| accepted-oracle-3 | 2.449111 | 7.795265 | 0.378237 | 0.329348 | 10.951963 |
| accepted-control-price | 2.448657 | 7.890551 | 0.327966 | 0.248283 | 10.915457 |
| accepted-control-partial | 2.406952 | 7.839680 | 0.428061 | 0.272414 | 10.947108 |
| accepted-control-retry | 2.709245 | 7.760033 | 0.227525 | 0.223332 | 10.920135 |
| accepted-compat-metadata | 2.545734 | 7.954516 | 0.227649 | 0.198684 | 10.926583 |

全部正式运行均 ≤25 秒，无需拆包；30 秒硬上限未改变。本次主机观测不保证另一主机相同耗时。

## 固定 Verifier 镜像

构建命令：

```bash
docker build --pull=false --network default \
  --tag samescale/minishop-fastapi-verifier:1.0.0 \
  /home/dev/.local/state/samescale-minishop-fastapi-1.0.0-audit/image
```

基础镜像 `python:3.12.14-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579`。构建文件及下载日志私有保管；镜像未含隐藏资产。运行一律通过现有 PinnedVerifierSandbox，使用上表完整镜像 ID、--pull never、network none、非 root、只读挂载及现有资源限制。

Dockerfile SHA-256 `sha256:b1d86b011ce4e9ab7157cb8e3cd8fc5757a8db1deaa402a2a0b75635eeae9071`；依赖锁 SHA-256 `sha256:12dcf3544c5eef1fd20fdf21106939d552a90ca7d303ccfefc98b1ed55822459`。

13 个运行依赖：annotated-doc 0.0.5、annotated-types 0.8.0、anyio 4.14.2、click 8.4.2、fastapi 0.141.1、h11 0.16.0、idna 3.19、pydantic 2.13.4、pydantic-core 2.46.4、starlette 1.6.0、typing-extensions 4.16.0、typing-inspection 0.4.4、uvicorn 0.52.4。版本及下载哈希来自仓库锁；安装使用 `--only-binary=:all: --require-hashes`。构建联网只用于依赖下载，资格运行无网络。

## 回归验证、排除与公开泄露检查

新增 5 个公开摘要一致性检查追加到已有 Fast CI 核心模块 `tests/test_local_init_script.py`，不执行隐藏源码。原 18 个函数/类 AST 不变，既有 CI selectors/shards 清单不变；不删除、放宽或跳过既有断言。最终 focused：5 passed / 38 deselected（3.29 秒）。

uv 0.12.5；`uv run --locked ruff check .`、`uv run --locked ruff format --check .`、`uv run --locked mypy src tests scripts` 已通过（src/tests/scripts 的格式及 mypy 均为 472 文件）。全量 pytest 重跑完成：2157 collected / 2157 passed / 0 failed / 0 errors / 0 skipped / 0 deselected，pytest 页脚 1413.65 秒，含 uv/进程启动的整次调用 1417.58 秒；离线命名空间回归已 237 PASS（47.42 秒），两次 Replay、五个固定摘要一致，外部/Provider/模型/Judge 调用为 0。

首次全量调用继承了保管私有产物用的 umask 077，导致既有
`test_vault_rejects_missing_or_public_roots` 的 0755 目录前置条件实际成为 0700，
出现 DID NOT RAISE。保留原日志及中断记录（pytest 页脚 1 failed / 1254 passed；
完整收集为 2157，尚未完成的测试不计通过），不修改既有实现或断言。
同一测试在子进程 umask 022 下单项复测 1 PASS；随后使用全新测试数据库、
相同九项整文件排除、常规 umask 022 从头重跑全量。资格任务的隐藏材料仍以 0600/0700 保管。

提交前将仓库 diff 写到私有 state 根，只用私有标识清单检查，不把清单内容写入公开记录。
命令与结果：9 个 oracle/Verifier 独有标识，0 命中（rg 无命中退出码 1）。

```bash
SS_STATE=/home/dev/.local/state/samescale-minishop-fastapi-1.0.0-audit
git diff --cached --binary --no-ext-diff \
  1432cb94fc22e110e49e733bab7b96dc7d360a09 > "$SS_STATE/leak-review/repository.diff"
rg --count-matches -F -f "$SS_STATE/private-leak-patterns.txt" \
  "$SS_STATE/leak-review/repository.diff"
```

受保护的 src、Official tasks、CI selector/shard 清单与原有测试函数/类 AST 均无改动；原冻结证据前后逐文件校验一致；
新增内容只有本报告/契约/公开摘要、授权及状态文档，以及已有核心模块内的五项摘要检查。

最终全量命令（DATABASE_URL 仅指向新建的一次性测试数据库，先执行 `uv run --locked alembic upgrade head`；子进程 umask 为 022）：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --locked pytest -p pytest_asyncio.plugin -q --durations=20 \
  --junitxml="$SS_STATE/regression-022/pytest.xml" \
  --ignore=tests/test_codex_current_setup.py \
  --ignore=tests/test_codex_harness.py \
  --ignore=tests/test_multi_harness.py \
  --ignore=tests/test_phase_f_claude_startup.py \
  --ignore=tests/test_phase_f_deepseek_startup.py \
  --ignore=tests/test_runtime_config_hygiene.py \
  --ignore=tests/test_verifier_lifecycle_handoff.py \
  --ignore=tests/test_cli.py \
  --ignore=tests/test_subscription_protocol_docker.py
```

全量 pytest 在独立一次性 PostgreSQL 18 测试数据库上运行，使用清理后的环境和隔离 HOME，无实际凭据。以下文件在收集前以 `--ignore` 整文件排除（排除不等于通过）：

```text
tests/test_codex_current_setup.py
tests/test_codex_harness.py
tests/test_multi_harness.py
tests/test_phase_f_claude_startup.py
tests/test_phase_f_deepseek_startup.py
tests/test_runtime_config_hygiene.py
tests/test_verifier_lifecycle_handoff.py
tests/test_cli.py
tests/test_subscription_protocol_docker.py
```

前八项为明确要求；最后一项由启动路径检查发现，protocol_stub 仍会执行实际 Codex CLI，因此一并排除。普通 Fake 后端、内存协议替身与真实 Agent CLI 分开处理；Fake 回归不建立真实模型结果。

## NOT_RUN / NOT_COVERED

- DeepSeek MiniShop 快照读取、复制、还原、源码/自测/自报检查与执行：NOT_RUN。
- 被测接口声明、被测 EvidencePolicy、被测独立验收及 3b：NOT_RUN，等待单独授权。
- 上述九个整文件的测试：NOT_RUN。
- 浏览器购物车操作、刷新恢复、实际前端下单、错误/空态交互、视觉和响应式：NOT_COVERED；HTTP 前端三项不能替代完整 A11。
- Windows 11 / DeepSeek Harness Desktop、原 Harness/模型版本及原执行事实：NOT_COVERED。
- 穷尽并发调度/故障、未固定的请求规范化、被测源码体积与依赖交付、说明文档清楚程度/命令充分性：NOT_COVERED。
- R 未要求的鉴权、reset、后台/支付/云部署及范围外安全观察：不计 PASS/FAIL，本阶段未作被测安全结论。
- Agent CLI、付费模型、Judge、新开发轮次、合并与部署：NOT_RUN。

公开机器摘要：[minishop-fastapi-sqlite-1.0.0.json](minishop-fastapi-sqlite-1.0.0.json)。最终资格入口为批准的私有 state 根下 `final-task-policy.json`，对应 `final-qualification.json`、`final-validation.json` 和 `final-inspection.json`；`FINAL_ADMISSION.json` 记录这些路径及摘要。完整外部资格记录只能由操作员在该根复核；本报告不公开隐藏源码、断言输入或资格工作区。
