# 私有 MiniShop Verifier 1.2.0 独立资格 — 2026-10-18

**资格通过，CUSTOM / 独立合成样本；没有新的真实 MiniShop 成绩。**
新版本 `minishop-fastapi-sqlite@1.2.0` 在原版本目录之外创建，旧 1.1.2 和旧资格保持不变。
只复用独立编写的合成 baseline/oracle 及兼容样本；没有使用真实交付代码作为资格输入。
新接口注册表特意不注册真实 MiniShop 摘要，原记录绑定与已消耗标记完全保留。

## 固定身份与语义

| 身份 | 摘要 |
| --- | --- |
| Task | `sha256:d9a2e34c58b7b0f7d132e2b17b7e3bb619af6e2f11b8e38c5b4369c103ac52ed` |
| Verifier | `sha256:4840af82da8ded3e9c19b506155f31e92407d4bb98b1d664604bb9e999c701a5` |
| Qualification | `sha256:61f78e0aee1be64f58be48c34070ae4f28ab1f489ef659d4f9b31abb0bf33b4b` |
| Interface registry | `sha256:89772e2d86cbff76b95967839965b49b24867bd177334ee2863ac14c7eca61f6` |
| Image | `sha256:5ad60dee2fb2d11aa75f8ec7cb08bf4fb491a9463dd13261fb589e8d6e64b297` |
| Original R | `sha256:31c93f958b80472ada981cc30f210d41d313bc23a7d27acc2ad4fd15f3070bdc` |

原镜像不重建，保留 Pydantic 2.14.1 与锁定依赖；无核心 verification/Sandbox/REAL_CODEX、
预算或仓库依赖更改。TaskStore 重新导入并检查 `eligible_for_planning=true`，资格来自本轮
全新 baseline/oracle 观察及隔离证据，没有继承 1.1.2 资格。

实现前固定语义并保留摘要：C05 接受成功且数据库计价，或安全 4xx 拒绝且商品/SQLite 逻辑状态
不变。两条路径均须在数据库价格更新后创建正常订单，核对明细、整数分金额、查询持久结果与库存。
C13 继续拒绝布尔数量且状态不变，明确其正整数商品数量的业务解释。其余 24 项检查体与套件
设置的 AST 保持相同；共用拒绝检查只增加诊断，不改变断言。

失败详情限定为异常类、阶段枚举、HTTP 状态、状态是否不变/库存是否符合预期；
断言尚未到达的状态核对明确未观察。启动/基础设施错误不输出应用日志、异常消息或完整 traceback。
实际全部失败详情通过允许字段与长度检查；完整响应、数据库内容和隐藏源码不进入详情。

## 每次物理观察

| 独立样本试次 | 通过项 | 失败项 | 整次秒数 |
| --- | --- | --- | --- |
| final-baseline-1 | 6/26 | C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21, C22, C25 | 9.907 |
| final-baseline-2 | 6/26 | C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21, C22, C25 | 9.622 |
| final-baseline-3 | 6/26 | C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21, C22, C25 | 9.848 |
| final-oracle-1 | 26/26 | — | 11.541 |
| final-oracle-2 | 26/26 | — | 11.686 |
| final-oracle-3 | 26/26 | — | 11.496 |
| final-control-price | 25/26 | C05 | 11.931 |
| final-control-partial | 25/26 | C17 | 13.177 |
| final-control-retry | 24/26 | C18, C20 | 12.901 |
| final-compat-metadata | 26/26 | — | 14.411 |
| final-compat-subject-shape | 26/26 | — | 14.275 |
| final-compliant-reject | 26/26 | — | 11.216 |
| final-control-forged | 25/26 | C05 | 11.181 |
| final-control-reject-all | 16/26 | C04, C05, C06, C07, C18, C19, C20, C21, C22, C25 | 8.763 |
| final-control-boolean | 25/26 | C13 | 13.005 |
| final-control-stale | 25/26 | C05 | 12.466 |
| final-control-reject-mutates | 25/26 | C05 | 11.449 |

baseline×3 均为有效业务 FAIL；oracle×3 均全项 PASS，各侧逐项向量一致。
`compliant-reject` 证明第二条合法金额处理路径；oracle 证明忽略额外字段后数据库计价路径。
伪造金额、拒绝全部订单、接受 bool、过期价格、拒绝时副作用、部分提交及幂等重复扣库存均被检出。
`control-forged` 与原 `control-price` 字节相同：是同一单点缺陷设计的两次观察，不算两个独立缺陷。
新控制均核对为单处源码变更；原三种单点缺陷也重新核对其原始 mutation 记录。

17 次合成样本物理执行，无重试，无运行时基础设施失败；均 26 个唯一检查、分数与逐项一致，
exit 0、无截断、输入/输出 workspace 摘要一致、清理完成且生命周期无失败。
全部低于既有 25 秒资格余量与 30 秒硬上限。network none、非 root、只读 bind/rootfs、
128 MB / 0.5 CPU / 64 PID 等边界沿用既有 Sandbox；兼容样本同时检查隐藏文件读取被拒绝。

## 失败历史、保管与限制

一次准备失败：复制旧只读包后写新 contract 触发 PermissionError，**0 次物理执行**。
保留失败副本，给新副本恢复私有可写权限后完成；没有删除历史记录或把准备错误算作业务 FAIL。
所有 17 次原始 result/summary、单点变更、构建身份、资格/验证/隔离文件留在 Git 外私有目录。
公开文件只有[脱敏资格摘要](minishop-verifier-1.2.0-20261018.json)，列出独立摘要与每次结果；
它不包含 hidden Verifier、Oracle 或资格源码，也不提供匿名完整复现。

未覆盖：真实 MiniShop 的新版本验收（明确禁止）、浏览器购物车/结算、视觉适配、Windows、
说明文档充分性、原开发/模型身份、全部并发调度与故障点。这里的浏览器限制针对 MiniShop；
官网展示另有实际浏览器验收。本轮真实 MiniShop 物理执行 **0 次**。
