# MiniShop FastAPI / SQLite 1.0.0 资格与回归摘要

本报告只公开契约索引、检查名称、摘要、耗时和计数；完整原文、适配声明、参考实现、隐藏检查和资格工作区均留在批准的 Git 外私有目录。本次为交付后审计资格，不是预注册盲测，尚无被测快照验收结论。

## 固定身份

| 项目 | 值 |
| --- | --- |
| task_reference | `minishop-fastapi-sqlite@1.0.0` |
| requirement_sha256 | `sha256:31c93f958b80472ada981cc30f210d41d313bc23a7d27acc2ad4fd15f3070bdc` |
| baseline_adapter_sha256 | `sha256:3bbbf6e5ae731b7af577ff765b488d31a2fbb2e1fb42ce576b33e9af3e783f85` |
| oracle_adapter_sha256 | `sha256:1d07ebd38a6119f2e03a7c25ef27b1bfeba94d31f651491278512e2cb376ec46` |
| task_digest | `sha256:ad6abc0ce6bffc579afaa21bfa210bc076a4d58d978017b481c6b9eec3f283fc` |
| verifier_digest | `sha256:caeba3d8e989660a5dd9c95d3b7a1857496a137e73a30d9bdbc36ddcd159ccd2` |
| qualification_identity | `sha256:6893bb82af55b0527357b92e7b538abcd12152b7baa347efe967be77b593d958` |
| image_id | `sha256:e8e919870821cd896510b4f29e073b37ac7a5b711f7edeea508606a2defb84a3` |
| eligible_for_planning | `True` |

fetch 后 `main=1432cb94fc22e110e49e733bab7b96dc7d360a09`；分支 `codex/minishop-fastapi-sqlite-1.0.0-audit`。原有脏工作区未修改；本阶段未读取、复制或运行 DeepSeek MiniShop 快照、源码、自测或自报。被测接口声明 NOT_WRITTEN，3b NOT_AUTHORIZED_NOT_RUN。

完整包 19 文件 / 59,161 字节；baseline 工作区 7 文件 / 6,551 字节，oracle 覆盖后工作区 7 文件 / 9,781 字节。R 是 UTF-8 原始字节，5,184 字节，无末尾换行；未增删原文字符。两份适配声明和 R 的摘要均计入任务 manifest metadata 和整个包的 task_digest。

## 资格、缺陷控制与逐项结果

三次 baseline 均正常启动、正常 SUBJECT_RESULT、6/26 通过（20 项业务失败）；三次 oracle 均 26/26 通过。两组各自逐项布尔向量一致，退出码均 0；无基础设施失败、超时、截断或清理失败。实际构造并导入最终独立 CUSTOM 资格后，TaskStore 再次 inspect 返回 eligible_for_planning=true、reason_codes=[]。

| 运行 | 分类 | 通过/检查数 | 整次秒数 |
| --- | --- | ---: | ---: |
| release-baseline-1 | SUBJECT_RESULT / FAIL | 6/26 | 13.013629 |
| release-baseline-2 | SUBJECT_RESULT / FAIL | 6/26 | 13.056358 |
| release-baseline-3 | SUBJECT_RESULT / FAIL | 6/26 | 11.469768 |
| release-oracle-1 | SUBJECT_RESULT / PASS | 26/26 | 13.709437 |
| release-oracle-2 | SUBJECT_RESULT / PASS | 26/26 | 14.677587 |
| release-oracle-3 | SUBJECT_RESULT / PASS | 26/26 | 14.998928 |
| release-control-price | SUBJECT_RESULT / FAIL | 25/26 | 13.999380 |
| release-control-partial | SUBJECT_RESULT / FAIL | 25/26 | 13.493666 |
| release-control-retry | SUBJECT_RESULT / FAIL | 24/26 | 14.331573 |

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

准备过程保留最初 3 次观察（baseline 7/26、oracle 26/26、另一次 baseline 7/26），
以及随后两个被替代版本的各 9 次完整观察。复核发现“静态脚本出现 API 字符串”会误伤动态
拼接 URL 的合法实现，因此最终 C25 改成网页/资源加载后的独立 HTTP API 场景，实际
JavaScript 行为仍 NOT_COVERED；C26 同时去除固定文件名/命令关键词要求，只观察说明文档
可读非空，说明是否清楚另列 NOT_COVERED。原版本包、资格、policy 和全部原始记录完整保留，
旧 TaskStore 不用于最终准入；最终版本使用独立的 release-managed-store 与 final-task-policy.json。
最后复核还发现顺序下单会消耗初始库存；因此在先检查原始目录后，通过临时测试数据库构造充足库存，不把 R 未固定的初始库存数值当作额外要求。
表中是这些变更后重新冻结身份的六次资格及三次单点缺陷控制，并未混用旧结果。
资格元数据复核修正了物化目录定位：使用实际随机创建的非空 workspace，重新核对两侧工作区摘要、文件清单与隐藏材料隔离，再从原始观察生成资格；原元数据留档，没有为此重跑 Verifier。总物理任务 Verifier 尝试为 30（最初准备 3、被替代版本 18、最终版本 9），没有自动重试，
没有为保留某次结果而删除失败记录。所有 30 次均 ≤25 秒；最初三次分别为
10.056985、11.992685、9.864582 秒；两个被替代版本的计数/耗时保留在公开 JSON 的
superseded_revision / superseded_revision_2 中，不充当最终 task_digest 的重复证据。

## 不重叠的分段耗时

整次从加载任务/准备独立工作区开始，包含容器预检、执行、清理、结果保存和私有权限恢复。下表各行五段之和等于整次；计时舍入误差小于 0.002 秒。

| 运行 | 镜像预检/创建 | 挂载/隔离检查 | start --attach | 容器清理 | 准备/保存/其余 | 整次 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| release-baseline-1 | 0.281000 | 0.063000 | 12.415000 | 0.123000 | 0.078629 | 13.013629 |
| release-baseline-2 | 0.376000 | 0.068000 | 12.417000 | 0.123000 | 0.072358 | 13.056358 |
| release-baseline-3 | 0.301000 | 0.048000 | 10.925000 | 0.132000 | 0.059768 | 11.469768 |
| release-oracle-1 | 0.293000 | 0.073000 | 13.132000 | 0.159000 | 0.071437 | 13.709437 |
| release-oracle-2 | 0.311000 | 0.050000 | 13.986000 | 0.123000 | 0.078587 | 14.677587 |
| release-oracle-3 | 0.438000 | 0.073000 | 14.293000 | 0.159000 | 0.067928 | 14.998928 |
| release-control-price | 0.350000 | 0.046000 | 13.388000 | 0.153000 | 0.062380 | 13.999380 |
| release-control-partial | 0.281000 | 0.048000 | 12.968000 | 0.125000 | 0.071666 | 13.493666 |
| release-control-retry | 0.328000 | 0.057000 | 13.741000 | 0.153000 | 0.073573 | 14.331573 |

`SANDBOX_START`、`PROCESS_START`、`PROCESS_WAIT` 记录同一次附加执行的重叠阶段；上表只取 SANDBOX_START，其他重叠时长不相加。start --attach 包括容器启动、整个 Verifier 主体及附加流返回，不能称为纯启动耗时。

Verifier 主体另用单调时钟记录服务启动、业务检查、服务停止和其余四段；均为主体内部的互斥区间，不与上一表叠加。检查段扣除了内部重启所占的服务启动/停止时间。下面服务启动/停止包含重启涉及的进程，具体次数不是 API 成功计数。

| 运行 | 服务启动 | 业务检查 | 服务停止 | 其余 | 主体合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| release-baseline-1 | 3.124903 | 7.760626 | 0.428806 | 0.528316 | 11.842650 |
| release-baseline-2 | 3.194980 | 7.788030 | 0.428289 | 0.517095 | 11.928394 |
| release-baseline-3 | 2.947198 | 6.633245 | 0.379467 | 0.470593 | 10.430504 |
| release-oracle-1 | 2.861821 | 9.156014 | 0.230627 | 0.403364 | 12.651826 |
| release-oracle-2 | 3.116711 | 9.638053 | 0.379673 | 0.414527 | 13.548963 |
| release-oracle-3 | 2.887942 | 10.028987 | 0.329182 | 0.571278 | 13.817390 |
| release-control-price | 2.746086 | 9.177306 | 0.428145 | 0.466742 | 12.818279 |
| release-control-partial | 2.637178 | 8.980561 | 0.428584 | 0.489621 | 12.535943 |
| release-control-retry | 2.985109 | 9.395738 | 0.428317 | 0.416543 | 13.225708 |

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

新增 5 个公开摘要一致性检查追加到已有 Fast CI 核心模块 `tests/test_local_init_script.py`，不执行隐藏源码。原 18 个函数/类 AST 不变，既有 CI selectors/shards 清单不变；不删除、放宽或跳过既有断言。最终 focused：5 passed / 38 deselected（4.58 秒）。

uv 0.12.5；`uv run --locked ruff check .`、`uv run --locked ruff format --check .`、`uv run --locked mypy src tests scripts` 已通过（mypy 472 文件；格式最终文件数另记）。全量 pytest 重跑完成后补入精确计数；离线命名空间回归已 237 PASS（47.42 秒），两次 Replay、五个固定摘要一致，外部/Provider/模型/Judge 调用为 0。

首次全量调用继承了保管私有产物用的 umask 077，导致既有
`test_vault_rejects_missing_or_public_roots` 的 0755 目录前置条件实际成为 0700，
出现 DID NOT RAISE。保留原日志及中断记录（pytest 页脚 1 failed / 1254 passed；
完整收集为 2157，尚未完成的测试不计通过），不修改既有实现或断言。
同一测试在子进程 umask 022 下单项复测 1 PASS；随后使用全新测试数据库、
相同九项整文件排除、常规 umask 022 从头重跑全量。资格任务的隐藏材料仍以 0600/0700 保管。

提交前将仓库 diff 写到私有 state 根，只用私有标识清单检查，不把清单内容写入公开记录。
命令与结果：7 个 oracle/Verifier 独有标识，0 命中（rg 无命中退出码 1）。

```bash
SS_STATE=/home/dev/.local/state/samescale-minishop-fastapi-1.0.0-audit
git diff --cached --binary --no-ext-diff \
  1432cb94fc22e110e49e733bab7b96dc7d360a09 > "$SS_STATE/leak-review/repository.diff"
rg --count-matches -F -f "$SS_STATE/private-leak-patterns.txt" \
  "$SS_STATE/leak-review/repository.diff"
```

受保护的 src、Official tasks、CI selector/shard 清单与原有测试函数/类 AST 均无改动；
新增内容只有本报告/契约/公开摘要、授权及状态文档，以及已有核心模块内的五项摘要检查。

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
