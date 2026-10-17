# MiniShop FastAPI / SQLite 1.0.0：交付后审计契约

本任务 `minishop-fastapi-sqlite@1.0.0` 是交付后审计的独立任务资格准备，
不是预注册盲测，不构成 DeepSeek 的验收结果、开发自测复核或模型能力结论。
权威依据仅为操作员提供的原始需求 R（交给原开发 Harness 的时间为
2026-10-16 03:36，UTC+8）。原文单独冻结，以下编号只是外部索引，不修改 R。
旧 `minishop-standard-library@1.0.0` 的 WSGI、内存状态与重启重置规则不适用。

## 原文索引与判定边界

`F1` 至 `F6` 分别指 R 的 Functional Requirements 第 1 至 6 节；
`F1.4` 表示第 1 节第 4 个项目符号。`F5.0` 指幂等键的引导句，
`F5.1` 至 `F5.4` 指其四项要求。`F6.1` 至 `F6.6` 指页面功能六个项目符号，
`F6.theme` 和 `F6.frontend` 指其后的主题/响应式与必须有可用前端两段。
`A1` 至 `A12`、`K1` 至 `K11`、`V1` 至 `V5` 分别指
Acceptance、Constraints、Verification 中的原编号。

资格只检查参考 fixture 和 baseline 的最终工作区契约。原开发者的操作历史、工具版本、
模型信息、自报与测试报告不在本阶段读取或核实；R 中针对原开发者的约束不会被当成本阶段
操作员的执行指令。技术资格沿用 CUSTOM / UNASSIGNED，不赋予 Official 或未见曝光身份。

业务失败要求服务已正常启动并产生非空的可解析逐项结果。服务启动失败、依赖或接口声明
错误、不可观察的存储布局、超时、非法输出、挂载/清理失败均为基础设施或适配问题，
不能冒充 baseline 的业务失败。零检查不能 PASS。资格必须满足三次 baseline 业务 FAIL、
三次 oracle 全项 PASS、对应逐项向量一致、固定全部身份、每次整次耗时不超过 25 秒。
现有 30 秒硬上限保持原样；超过 25 秒即停止并提交拆包方案。

## 接口适配契约

R 只固定 `GET /api/products`、`POST /api/orders`、
`GET /api/orders/{order_id}`，以及创建订单请求中的 `idempotency_key`。
不追加固定商品名称、价格、库存初始值、商品 ID、响应字段名、启动命令或数据库文件名。
正常创建/重试允许任何成功的 2xx；非法商品/数量及库存不足应为 4xx；
只有同键不同内容按 R 明确要求固定为 409。数据库故障注入允许错误响应，随后必须无部分提交。

每个 fixture 的独立 `interface.json` 只声明接口形状：

| 分组 | 内容 |
| --- | --- |
| `schema_version` | 声明格式版本 1 |
| `startup` | Uvicorn 的 `module:attribute`、数据库环境变量名、以 `{tmp}/` 开头的数据库路径模板 |
| `routes` | 首页、商品列表、创建订单和订单查询路径 |
| `products` | 列表容器及 ID、名称、整数分价格、库存、描述的 JSON 字段路径 |
| `request` | 明细列表、商品 ID、数量、幂等键及客户端价格/金额字段名 |
| `order` | 响应容器、订单 ID、金额、明细及明细商品 ID/数量/价格的 JSON 字段路径 |

路径使用点分隔，空容器路径表示响应根；适配声明不能带业务期望、分数、容错规则、
预期库存/金额、测试分支或内联可执行代码。启动由固定 Python/Uvicorn 进程执行，
数据库写入沙箱 `/tmp`。两份声明分别冻结摘要，并进入任务 manifest metadata，
整个包的任务摘要同时绑定 R 和声明字节。工作区 `protected_paths=[]`。

本阶段仅冻结 baseline 与独立 oracle 的声明；两者有不同字段名。
尚未编写、推测或读取被测快照的声明。3b 前须另行人工审查并冻结被测声明，
核对其只描述接口形状、适用于所批准快照，记录单独摘要与最终绑定身份；
不能因资格成功而自动运行被测快照。接口或任务字节变化后须重新检查资格身份，
不能挪用旧资格。此说明不授权 3b。

SQLite 商品观察通过 API 返回值和数据库反射关联实际记录，不硬编码表名或列名。
检查原始目录后，在测试数据库构造足够库存的下单前置条件，不把初始库存数值或检查顺序造成的库存消耗当作 R 额外要求。
故障注入使用临时测试数据库中的 SQLite 触发器，既不依赖应用的管理/reset 接口，
也不把应用提供这些接口列为要求。无法唯一关联商品记录的特殊存储布局必须先报告
适配/观察限制，不能直接判业务失败。持久化证据同时包括 SQLite 状态变化，以及只迁移
SQLite、使用新运行目录和新进程后返回的完整订单/明细/库存；不固定订单存储表结构。
有限并发及故障注入只支持本组具体条件下的观察，不证明所有调度或所有故障点。

## 检查项与 R 的具体映射

每次执行下列相同的 26 项；非法输入拒绝同时核对商品状态和数据库逻辑记录不变。
金额语义为整数分，数量为正整数；布尔值、非整数、空值和缺字段属于非法数量。

| ID | 公开检查名称 | R 条款 | 可验证语义 |
| --- | --- | --- | --- |
| C01 | catalog_fields_and_minimum | F1.1–F1.4；A1 | 至少三种商品，名称、描述、整数分价格和库存可取 |
| C02 | sqlite_integer_prices | F1.4–F1.5；Context 技术栈 | SQLite 中关联商品的价格是整数分 |
| C03 | catalog_database_authority | F1.5；F4.6 | 测试数据库的价格/库存变化由商品 API 如实返回 |
| C04 | create_and_query_order | F3.1–F3.3；A3–A4 | 创建并查询同一订单，包含正确明细、编号和整数分总金额 |
| C05 | server_repricing_ignores_amounts | F2.4；F1.4；A4 | 篡改客户端金额与单价仍按数据库价格重新计价 |
| C06 | sqlite_order_and_line_persistence | F3.4–F3.5；A10 | 下单改变 SQLite 持久状态；与 C22 合证订单及明细从 SQLite 恢复 |
| C07 | stock_decrement | F4.3；A5 | 成功下单按数量扣库存 |
| C08 | insufficient_stock_rejected_unchanged | F4.1–F4.4；A6 | 超库存请求拒绝，状态不变 |
| C09 | unknown_product_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 非法商品拒绝，状态不变 |
| C10 | zero_quantity_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 零数量拒绝，状态不变 |
| C11 | negative_quantity_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 负数量拒绝，状态不变 |
| C12 | fractional_quantity_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 非整数数量拒绝，状态不变 |
| C13 | boolean_quantity_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 布尔数量拒绝，状态不变 |
| C14 | null_quantity_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 空数量拒绝，状态不变 |
| C15 | missing_quantity_rejected_unchanged | F4.1、F4.4、F4.6；A7 | 缺数量拒绝，状态不变 |
| C16 | multiline_failure_rolls_back | F4.2–F4.4；A6 | 多商品中一项失败时，其余库存及订单均不部分提交 |
| C17 | injected_database_failure_rolls_back | F4.3–F4.4 | 数据库插入失败后，无只扣库存或不完整订单 |
| C18 | same_key_retry_returns_original | F5.0–F5.2；A8 | 同键同内容返回原订单，库存只扣一次，持久状态不变 |
| C19 | same_key_changed_content_conflict | F5.3 | 同键不同内容返回 409，状态不变 |
| C20 | concurrent_same_key_single_order | F5.4；A8 | 同键同时请求返回同一订单，库存只扣一次 |
| C21 | concurrent_orders_do_not_oversell | F4.5；A9 | 多个不同键并发争用库存，不超卖、不出现负库存 |
| C22 | restart_preserves_order_and_stock | F3.4–F3.5；A10 | 只迁移 SQLite 到新运行目录后，完整订单、明细与库存一致 |
| C23 | frontend_html_loads | F6.frontend；F6.1–F6.6；A1、A11（部分） | 首页通过 HTTP 返回 HTML |
| C24 | frontend_local_resources_load | F6.frontend；A11（部分） | 页面引用的本地资源可通过 HTTP 加载 |
| C25 | page_and_api_http_scenario | F1.3；F3.1；F5.0；F6.frontend；A11（部分） | 加载首页与资源后，独立 HTTP 客户端按声明完成商品/下单/查询场景；不执行 JS |
| C26 | local_start_and_test_documentation | A12；Context 技术栈 | 可读取非空说明文档；启动/测试说明的清楚程度与任意命令正确性未覆盖 |

C23–C25 不执行 JavaScript，不证明页面可实际完成下单；即使全部通过，A11 的完整要求
仍是 `NOT_COVERED`。C26 仅观察说明文档可读且非空；启动/测试说明的清楚程度为 `NOT_COVERED`。
不固定文档文件名或命令拼写，不执行被测自测，也不验证文档中的任意命令都能成功。
资格 fixture 的真实启动与 API 检查由本任务独立执行，不读取原开发者的测试或报告。

## NOT_COVERED 与范围外观察

| 类别 | 条款或项目 | 状态与理由 |
| --- | --- | --- |
| 浏览器交互 | F2.1–F2.3；A2 | NOT_COVERED：添加、移除、改量、实时合计、刷新恢复需浏览器交互 |
| 实际前端结算 | F6.1–F6.6；A11；V5 | NOT_COVERED：未执行浏览器点击、空态及错误提示交互 |
| 视觉与响应式 | F6.theme | NOT_COVERED：白色主题、协调布局、断点表现不由 HTTP 断言证明 |
| 原开发环境 | Context 的 Windows 11 / Harness Desktop | NOT_COVERED：资格运行在 Linux Docker，不验证 Windows 行为 |
| 说明文档充分性 | A12（部分） | NOT_COVERED：仅核对说明文档可读非空，不以固定关键词判断语义或执行原自测 |
| 原开发执行事实 | V1–V5、最终输出、K1–K11 的历史遵守情况 | NOT_COVERED：不读取源码、自测、自报、执行记录或工具凭据 |
| 全空间并发/故障 | F4.4–F4.5、F5.4 | NOT_COVERED：有限条件观察不能穷尽调度、进程崩溃、断电、磁盘故障 |
| 输入规范化细节 | 重复商品行、重排、键空白、数字字符串等 | NOT_COVERED：R 未固定等价内容的规范化协议，不新增判分要求 |
| 依赖与源码交付体积 | K6–K7 | NOT_COVERED：本阶段未检查被测快照，资格 fixture 清单另记 |
| 登录、支付、物流、后台、云部署 | R Context 明确排除 | OUT_OF_SCOPE，不计 PASS/FAIL |
| 商品创建鉴权、reset/管理接口、限流等 | R 未要求 | OUT_OF_SCOPE_SECURITY_OBSERVATION；本阶段不作被测安全结论，不计 PASS/FAIL |
| 启动器/模块代码恶意对抗、隐藏材料窃取 | R 未定义对抗协议 | OUT_OF_SCOPE；现有沙箱边界不等于不同进程用户隔离证明 |

## 固定环境与私有保管

使用现有 [PinnedVerifierSandbox](../src/harnesslab/local_execution/sandbox.py)，
运行时 `--pull never`、network none、UID/GID 10001、128 MB、0.5 CPU、64 PID，
根文件系统、`/workspace` 与 `/verifier` 只读，只有 16 MB `/tmp` 可写。
固定基础镜像 digest，全部 13 个运行依赖均精确版本且使用 `--require-hashes`；
构建联网仅供下载这些依赖，镜像不包含 oracle、hidden verifier 或资格工作区。
每个 EvidencePolicy 仍只允许一个 verifier_image_id，本阶段不创建被测 EvidencePolicy。

操作员批准的包根为 `/home/dev/.local/share/samescale/task-snapshots`，
独立 policy/state 根为 `/home/dev/.local/state/samescale-minishop-fastapi-1.0.0-audit`。
R、完整包、oracle、hidden verifier、两份适配声明和资格工作区均在 Git 外。
私有保留文件 0600、目录 0700；现有沙箱仅对运行副本临时增加容器读取权限，
私有父根保持 0700，执行后恢复副本 0600/0700，staging 经现有 lifecycle 清理。
不修改 sandbox、`external_evidence/*`、`verification.py`、收据、Replay/export、身份算法、
REAL_CODEX 门禁或 30 秒上限。不读取凭据，不调用付费模型，不启动 Agent CLI。

固定身份、逐项公开结果、每次耗时、缺陷控制、测试计数与 NOT_RUN
见[资格与回归摘要](qa/minishop-fastapi-sqlite-1.0.0.md)。
本阶段完成后等待人工审查及单独 3b 授权，不合并、不部署、不执行被测快照。
