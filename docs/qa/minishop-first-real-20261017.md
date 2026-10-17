# 真实 MiniShop 首次独立 L0 验收 — 2026-10-17（Asia/Shanghai）

**最终状态：VERIFIED_FAIL，24/26 PASS，C05 / C13 业务失败。一次且仅一次物理 Verifier；没有重试。**

本轮用户已明确授权该固定记录的一次物理尝试。前检完全匹配后，通过原 `harnesslab external-evidence verify-workspace … --confirm-independent-verifier` CLI 执行；没有改 MiniShop、接口声明、Verifier、任务、预算或历史收据，没有 Coding Agent、LLM、Provider 或 Judge 调用，没有合并、部署或修改业务服务。后续操作只读取保存材料。

## 身份与执行

| 项目 | 核对值 |
| --- | --- |
| 代码基线 / PR #30 | `68fd2f1d4bef57b44c25e50f6fddbe6174c40b45` |
| Record | `5fe073a6d1999fabf61945917bd297ac784addf1809f078e75817764df0f7086` |
| Task | `minishop-fastapi-sqlite@1.1.2` |
| Task digest | `sha256:78e8c1945d0df60610923c1989960142f322419ee42f47354b00302ee0639b35` |
| Verifier | `sha256:b8ee081681a71fc198dfe00cd84cf29f9441913cf718109f33e74825dbf9edf9` |
| Qualification | `sha256:16c02a254dc7b296776f193cb89032ee67d8cfda5a48e1d4df9bc229cc08cd7e` |
| Image | `sha256:5ad60dee2fb2d11aa75f8ec7cb08bf4fb491a9463dd13261fb589e8d6e64b297` |
| Registry | `sha256:a06e5d7da92b8b73615a13688143e4f409c37e91c02e340c083fbe12992f7092` |
| Shape declaration | `sha256:72f12eaa8ec62106f8bcc7def0b6685a6b2a40ab82c3b1360c5a5a7e127065ef` |
| Policy | `sha256:ac1f5e48eb919fd393bf6c0cb1a8d196081df12c859a7b503669b6b139f216e8` |
| Snapshot | `2fd1898f67aadfee85fdf40f924cccf68d64759443d125715bacec6e91d7ec68` |
| Content | `sha256:2665fbe6ae797a8c075cb92894610fded920f0ebcbf63fadb39ef567661eb143` |
| 原快照序列化文件 | `sha256:846222ebfc7a626bfe979ae580d49677f2a2368da7bdfbc5ef4c3047c38927a0` |
| 开始 | `2026-10-17T18:46:11.738466+08:00` |
| 结束 | `2026-10-17T18:46:26.685717+08:00` |
| CLI 全程耗时 | `14.947336 秒` |
| 容器执行时间 | `10810 ms` |
| 物理次数 / CLI 次数 / Docker create/start/destroy | `1 / 1 / 1/1/1` |

前检 TaskStore eligible=true；目标无任何已消耗标记/收据，runtime/artifact 不存在；32 文件 / 237,995 字节与恢复源、记录工作区和原 CodeSnapshot 逐字节相同。Linux Docker、固定镜像和 Landlock ABI 8 已核对。正式预算仍为 30 秒。

容器 exit 0，报告解析完整且 26 个名称唯一，score=24/26，总判定与逐项一致；无 timeout、cancel、截断或基础设施失败。exit 0 表示 Verifier 完成，业务结果为 FAIL。记录新增一次尝试和不可重复启动标记；容器 create/start/destroy 各一次。C22 内部的业务重启属于这同一次固定检查，不是第二次物理 Verifier。

## C01–C26

| 项 | 名称 | 本次结果 | 公开验收语义 |
| --- | --- | --- | --- |
| C01 | catalog_fields_and_minimum | PASS | 至少三种商品，名称、描述、整数分价格和库存可取 |
| C02 | sqlite_integer_prices | PASS | SQLite 中关联商品的价格是整数分 |
| C03 | catalog_database_authority | PASS | 测试数据库的价格/库存变化由商品 API 如实返回 |
| C04 | create_and_query_order | PASS | 创建并查询同一订单，包含正确明细、编号和整数分总金额 |
| C05 | server_repricing_ignores_amounts | **BUSINESS FAIL** | 篡改客户端金额与单价仍按数据库价格重新计价 |
| C06 | sqlite_order_and_line_persistence | PASS | 下单改变 SQLite 持久状态；与 C22 合证订单及明细从 SQLite 恢复 |
| C07 | stock_decrement | PASS | 成功下单按数量扣库存 |
| C08 | insufficient_stock_rejected_unchanged | PASS | 超库存请求拒绝，状态不变 |
| C09 | unknown_product_rejected_unchanged | PASS | 非法商品拒绝，状态不变 |
| C10 | zero_quantity_rejected_unchanged | PASS | 零数量拒绝，状态不变 |
| C11 | negative_quantity_rejected_unchanged | PASS | 负数量拒绝，状态不变 |
| C12 | fractional_quantity_rejected_unchanged | PASS | 非整数数量拒绝，状态不变 |
| C13 | boolean_quantity_rejected_unchanged | **BUSINESS FAIL** | 布尔数量拒绝，状态不变 |
| C14 | null_quantity_rejected_unchanged | PASS | 空数量拒绝，状态不变 |
| C15 | missing_quantity_rejected_unchanged | PASS | 缺数量拒绝，状态不变 |
| C16 | multiline_failure_rolls_back | PASS | 多商品中一项失败时，其余库存及订单均不部分提交 |
| C17 | injected_database_failure_rolls_back | PASS | 数据库插入失败后，无只扣库存或不完整订单 |
| C18 | same_key_retry_returns_original | PASS | 同键同内容返回原订单，库存只扣一次，订单与库存语义不变 |
| C19 | same_key_changed_content_conflict | PASS | 同键不同内容返回 409，状态不变 |
| C20 | concurrent_same_key_single_order | PASS | 同键同时请求返回同一订单，库存只扣一次 |
| C21 | concurrent_orders_do_not_oversell | PASS | 多个不同键并发争用库存，不超卖、不出现负库存 |
| C22 | restart_preserves_order_and_stock | PASS | 只迁移 SQLite 到新运行目录后，完整订单、明细与库存一致 |
| C23 | frontend_html_loads | PASS | 首页通过 HTTP 返回 HTML |
| C24 | frontend_local_resources_load | PASS | 页面引用的本地资源可通过 HTTP 加载 |
| C25 | page_and_api_http_scenario | PASS | 加载首页与资源后，独立 HTTP 客户端按声明完成商品/下单/查询场景；不执行 JS |
| C26 | local_start_and_test_documentation | PASS | 可读取非空说明文档；启动/测试说明的清楚程度与任意命令正确性未覆盖 |

C05 与 C13 的原始报告 detail 均为 `AssertionError`。报告没有保存失败断言的具体位置、逐请求 HTTP 响应或数据库变更明细，因此不能据此断言 C05 本次具体返回 422、确实信任了客户端金额，或 C13 的某个特定校验层/库导致失败。失败范围是上述完整检查的语义未满足，不扩展成未经核实的根因。没有为定位失败再次请求应用。

## 证据完整性、隔离及清理

| 材料 | 摘要 |
| --- | --- |
| Receipt canonical digest | `sha256:104b423188e049276c00ea019424443140af0695926a7a98196669e0a6af61ed` |
| Receipt file SHA-256 | `sha256:65d49578345d55556b32375061e311640fa860fa0e1e69e81be3e306a32f8daf` |
| Verifier raw stdout / report | `sha256:c706ddc0cfcb3f3275377d0dc0994826cb38b38cfac65712f034d728f5cb70b8` |
| Manifest canonical digest | `sha256:0469cdb1a26709ca51ab56940aa092d041b46778b321ee59dae1d1b379d242da` |
| Lifecycle digest（仅原收据保存） | `sha256:ff182ac6ed9af6ab7443bd8059624579dd65b42d4daf6960d8c6be6e486ed46b` |
| Evidence export | `sha256:5bebdcd4e581467070626880e419dc2a1eb1358a24cbf3a0f205782c41ea2191` |

原始 `verification.json` 与 CLI 输出逐字节相等；现有 receipt reader 校验通过。raw stdout、stderr 的文件/流摘要和 manifest canonical digest 均重算匹配原收据。原记录的 `original_acceptance=NOT_VERIFIED`、`NO_RUN_RECORD` 和 `NOT_ATTESTED` 保持原样；本次独立工作区结果另存，不回填原开发过程。

实际 manifest：network none、UID/GID 10001、rootfs 与 `/workspace` / `/verifier` bind 均只读、128 MB / 0.5 CPU / 64 PID、drop ALL、no-new-privileges、默认 seccomp、无 Docker socket/额外设备/端口映射。`cleanup_verified=true`，对应容器已不存在，runtime 为空。输入、输出和保存的 artifact workspace 均为同一 content digest；110 个前检固定文件及 2,016 个旧资产/历史文件字节不变。

现有 CLI 仅在收据中保存 lifecycle 摘要，不单独持久化完整 lifecycle 对象；本轮无法独立重算该对象的摘要。固定核心代码在生命周期无失败且清理通过时才接受该收据，另有实际 manifest、空运行目录和 Docker destroy 事件交叉核对；没有重建或伪造逐阶段时序。

## 导出与离线 Replay

使用现有 `export_record` 导出 **327,992 字节**，完整工作区与独立收据绑定在 `evidence-export.json`，`hidden_assets_included=false`。导出包含原始交付源码及自报，因此只保存在私有审计目录，不提交 Git。

两次单独进程执行现有 `scripts.replay_external_evidence`，在 `unshare --net` 网络命名空间内，使用不同 Python hash seed；现有 audit guard 禁止网络/子进程调用。两次退出 0、输出逐字节相等，均为 Replay integrity PASS；其中工作区验收仍为 **VERIFIED_FAIL / 24/26**。subject_executed=false、verifier_executed=false、external_calls=0。Replay 只验证已保存证据一致性，不构成新的验收或来源认证。

## 与 DeepSeek 原有自测声明对照（静态读取，没有运行自测）

`MiniShop/docs/SELF_REPORT.md` SHA-256：`sha256:6465d8a1d95bd90c56059da391c9bf78613aab6fca3654c7d3dad01fdd7e65a0`。原文声明 `MINISHOP_SELF_REPORT=PASS`、91/91 pytest、22/22 HTTP 冒烟、30/30 浏览器及重启持久化 PASS。这里只把它们作为交付方声明：32 文件快照没有其引用的 artifacts 原日志/截图，也没有原生运行记录，无法核实历史自测次数、真实性、实际模型或平台。

| 对照范围 | 本次独立证据与判断 |
| --- | --- |
| 商品/整数分价格/正常订单/库存/幂等/有限并发/持久化 | C01–C04、C06–C12、C14–C22 PASS，与自报这些方向的一般行为声明相符；不同用例不合并成对原自测的复现。 |
| 金额字段 | 自报第 6 节、README 269–270 行声明额外金额字段直接 422。静态自测 `test_orders_api.py:105–119` 也把 422 当通过，然后另发不带伪造金额的请求。这与已冻结 C05“忽略客户端金额并按数据库价格完成下单”的断言不同；本次 C05 FAIL。不能把这个 FAIL 写成已经证明服务端使用了伪造金额。 |
| 非法数量 | 自报第 2 节第 7 场景称非法数量被拒绝。本次零/负/非整数/null/缺字段均 PASS，布尔数量拒绝且状态不变的 C13 FAIL。静态查看订单 API 自测，数量拒绝参数有 0、负数、超上限整数，未见专门的布尔数量拒绝用例；此为所读文件的覆盖观察，不是完整自测套件覆盖审计，也不确定运行根因。 |
| 前端/浏览器 | 自报 30/30 浏览器检查；本次 C23–C25 仅 HTML、资源及独立 HTTP 场景 PASS，未执行 JavaScript/鼠标/购物车/结算。不能复核其浏览器或视觉声明。 |
| 平台及说明文档 | 自报 Windows 下开发、Linux/macOS 未测；本次补充一次隔离 Linux 下 26 项的实际结果，不证明 Windows/WSL2。C26 仅说明文件可读，不验证其说明充分性或全部命令。 |

因此交付方“自测全通过”与本次独立契约 FAIL 可以同时成为各自范围的记录。没有证据将差异归因为欺骗、模型能力或 Harness 缺陷；不依据自报修正失败或放宽原断言。

## 未覆盖与交付位置

未覆盖：浏览器购物车与真实结算、视觉/响应式、说明文档清楚程度、Windows/WSL2/macOS、原开发执行事实/模型来源、所有故障点和并发调度，以及范围外的支付/物流/登录/部署。没有新增平台功能、代码修复、全库回归或付费调用。

私有审计根：`/home/dev/.local/state/samescale-minishop-first-real-20261017`。关键文件：

- `preflight.json`、`authorization.json`、`invocation.json`、`invocation-result.json`：匹配前检、授权范围及唯一 CLI 调用。
- `verification.original.json`、`verification-attempt.original.json`、`verifier-started.original.txt`：逐字节保存原收据与一次尝试标记。
- `sandbox-manifest.original.json`、`verifier-report.original.json`、`verifier-stderr.original.txt`、`docker-events.jsonl`：原执行产物与容器事件。
- `checks.json`、`audit.json`：26 项、摘要与隔离/清理核对。
- `evidence-export.json`、`replay-a.json`、`replay-b.json`、`replay-summary.json`：私有导出及双进程离线 Replay。
- `self-report-static-review.json`：原自报/自测文件摘要与静态定位。
- `SHA256SUMS.json`、`completion.json`：最终证据清单与冻结后完整性检查。

原收据保持在 `/home/dev/.local/state/samescale-minishop-trusted-interface-20261017/subject-records/5fe073a6d1999fabf61945917bd297ac784addf1809f078e75817764df0f7086/verification.json`；原 Sandbox artifacts 也保持在同一准备根的 `subject-artifacts/` 下。

**STOP：唯一物理尝试已消耗，等待用户审查。没有再次运行 verify-workspace。若需要修复或任何新物理验收，须单独界定并授权；不得删除原标记/收据来复用本记录。**
