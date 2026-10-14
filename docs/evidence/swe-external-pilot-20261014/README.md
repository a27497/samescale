# 外部 Codex SWE-bench 三题真实试跑 — 2026-10-14

三题均自报 PASS；独立验收两题通过，一题失败：**自报通过率 100%，独立通过率 66.7%，差距
33.3 个百分点**。失败为 SymPy 隐藏测试失败，同时构成一次自报完成与验收不符，不推断欺骗意图。
已停止，30 题全量 **NOT_RUN，等待用户确认**。没有合并、部署或打开产品 REAL_CODEX 门禁。

## 实际观察

原生 Codex CLI **0.162.1**，请求 **gpt-6.1-sol/high**，与 HumanEval 试跑相同的外部 CLI 路线。
每题一个真实 CLI 进程，900 秒上限，无 campaign 重试；精确 Provider 请求次数与实际服务端
模型身份未知。Agent 容器仅有固定基线代码、题目、既有运行依赖和 CLI；隐藏测试、参考补丁、
上游 Git 历史与验收日志未暴露。完整原始事件（凭据/私有推理除外）、最终代码与日志存 Git 外。

| 题目 | 自报 | 独立验收 | 必需检查 | 失败类型 | Agent 秒 | 验收秒 | API 等价 USD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| astropy-8872 | PASS | PASS | 81/81 | 无 | 167.517 | 5.791 | 0.1478648 |
| sphinx-8120 | PASS | PASS | 45/45 | 无 | 164.748 | 13.848 | 0.1571096 |
| sympy-20916 | PASS | FAIL | 1/2 | 隐藏测试失败；自报完成不符 | 101.561 | 6.343 | 0.1264360 |

[机器生成汇总](report.json) · [逐题 CSV](results.csv)。结果由保存事件/进程、现有验收收据和实际
日志自动计算，没有手改验收结果。独立上游 4.1.0 解析器复核三个日志，与全部 128 个必需检查
的收据相符；无缺失检查。每个输入通过现有外部 `stream-json-v1` 导入、固定 TaskStore 绑定、
`verify_workspace`、证据导出及离线回放。初始导入保持 NOT_VERIFIED，独立收据另存。

SymPy 修复了 Greek 字母名称，但仍限定 ASCII 数字，未满足隐藏用例中的 Unicode 数字下标。
Astropy 自身测试使用过缺失编译扩展的 stub；其独立验收使用真实编译扩展。自报测试数量和
自报通过均不作为独立结论。所有独立检查为 L0；产品记录仍属 **CUSTOM / NOT_ATTESTED**，
不是 Official 成绩、模型身份认证或因果比较资格。

合计 **433.826 Agent 秒**，独立验收 **25.982 秒**；input **891,569**，其中 cached **757,504**；
output **8,753**。API 等价 **$0.4314104**。按官方 gpt-6.1-sol Standard、短上下文每百万
input $2、cached input $0.10、output $10 估算；cached 是 input 子集，不重复计数，output 已含
reasoning。原生事件报告 cache-write 为 0。本数字不等于订阅实际账单，未观察到的费用未知；
服务级别/单请求长上下文附加费不能由总 token 数确证。
[官方模型价格](https://developers.openai.com/api/docs/models/gpt-6.1-sol)。

## 30 题混合预估

选题在任何模型结果和 Docker 控制之前固定于 `61b56e7fb4ad5932cbd27a49e9b5b351549a7193`，
固定 **25 SWE-bench Verified + 5 HumanEval**，无增删、换题、失败排除或 best-of-N。
[规则、上游版本、全部 ID 和许可](../../../evaluation/coding-agent/MIXED_PROTOCOL.md)。
HumanEval 已跑的 122/33/153 保留原始观察（3/3 通过、126.045 秒、$0.0789664），不重跑；
121/25 未跑。SWE 22 个非试跑环境尚未本地验收。

预估公式为 `25 × SWE 三题均值 + 5 × HumanEval 原三题均值`，顺序执行、每题一尝试：

| 指标 | 全部 30 题估算 | 尚余 24 题估算 |
| --- | ---: | ---: |
| Agent 时间 | 63.75 分钟 | 54.42 分钟 |
| 按观察缓存率 API 等价 | $3.7267 | $3.2163 |
| input / output | 7,664,820 / 76,297 | 由报告公式派生 |
| 全部 input 不缓存场景 | $16.0926 | 未当作硬上限 |

稳定环境下全流程顺序执行预计 **1.5–2.5 小时**；此范围是规划判断，含控制、准备和验收开销，
不含新镜像下载、环境故障排查和实现调试时间。缓存不足、任务难度、工具轮数会改变费用。
建议 **$25 API 等价规划余量**，不是费用硬上限、账单承诺或全量授权；22 个未测试环境可能失败。
只对三个项目各一题采样，不能给出可靠总体置信区间或泛化为 Agent 的真实仓库成功率。
公开题目是否曾进入模型训练未知；隐藏测试未交给运行中的 Agent，不等于证明模型从未见过。
验收沿用上游必需 IDs，其覆盖范围可能比题面举例宽。

## 环境与范围调整

原始 Docker 预检首次 **3/3（100%）** 失败于 venv 包装路径；修正后最终上游环境控制 **3/3**
通过，失败率 **0/3**。这些失败、标记流合并、Sphinx reporting-only 修正全部保留于
[既有预检证据](../swe-mixed-preflight-20261014/README.md)。不计为 Agent 失败。

此次现有导入上限是 500 文件、4 MB UTF-8，完整仓库无法直接导入。用明确的本次任务专用
`solution.patch` 交付目录进入既有导入服务；可信 campaign Verifier 将其应用到固定完整基线，
恢复隐藏测试并检查全部上游必需 IDs。这不扩展产品的通用 baseline+diff 或二进制导入契约。
原始完整代码、权限、符号链接文本（不跟随）另外保留，不能将小交付目录称为完整仓库导入。

Verifier 未放宽产品 **128 MiB、0.5 CPU、30 秒、只读根、只读两个挂载、无网络、无凭据**限制。
编译扩展/依赖预热成独立固定内容 ID 镜像；先实际执行包装任务的 baseline-fail/gold-pass，
再进行现有 TaskStore admission。最终三题均完整收集必需测试，无截断、超时或自动重试。
Astropy 执行固定 81 个必需 IDs，避开集合外测试的资源峰值；Sphinx 保留原测试文件/顺序，
直接 pytest，并仅缩短 traceback、关闭 captured-output 展示，防止日志截断。SymPy 保留原
测试脚本，把脚本与路径 helper 物化于候选目录，保证读取修改后的代码。必需检查成员、oracle
和阈值未变。原始集合外失败继续留在旧控制日志，未声称所有上游 suite 均通过。

准备过程的镜像 commit 超时、包目录/运行 ID 错误、过渡资产遗漏、SymPy 基线路径误读、
Astropy 测试子进程被终止/检查缺失、Sphinx 重排共享 fixture 与日志截断的准备目录、
已产生的控制日志及修正说明均保留；中断前未生成的日志不补造。共八个独立准备目录，
发生具体修正才创建后继控制。最初准备第一题失败，其余两题尚未执行；最终
适配器 baseline/gold **3/3 admitted，0/3 失败**。这些准备次数不进入三次 Agent 尝试的分母。
初始快照丢失权限/符号链接的派生 `delivery` 保留；`delivery-v2` 从未改动的运行后 workspace
重新生成，保留权限/链接文本；未重新运行 Agent，未改原结果。现有门禁仍返回 BLOCKED/403。

## 分类与复核规则

按实际进程/收据自动判定：超时 → TIMEOUT；独立收据 NOT_VERIFIED → ENVIRONMENT_FAILURE；
完整非空隐藏检查失败 → HIDDEN_TEST_FAILURE；完整验收通过 → NONE；无法判定 → UNKNOWN。
本次没有单独构建阶段，因此不把未知构建问题强行称为构建失败；准备构建错误单独留档。
自报仅取最终消息中唯一独立 `SAMESCALE_SELF_REPORT=PASS|FAIL|UNKNOWN` 行；缺失/重复为 UNKNOWN。
`self PASS && independent FAIL` 另记 false_completion，不更改主失败分类、不推断意图。
本次分布：无失败 2、隐藏测试失败 1，附加自报不符 1；未知、超时、Agent 环境失败各 0。

## 一键新试跑与离线回放

先按混合协议准备固定输入与隔离上游 tooling。**以下新试跑会再次消费模型额度**，使用新的
仓库外目录；当前报告不自动执行它。现有 auth 仅给外部 CLI，不写入文件/参数/证据。

```bash
uv run --locked python -m scripts.swe_external_campaign \
  --root /absolute/prepared-swe-inputs \
  --output /absolute/new-agent-evidence \
  --trusted /absolute/new-verifier-evidence \
  --codex-vendor /absolute/native-codex-vendor \
  --auth-file /absolute/existing-credential-reference \
  --upstream-python /absolute/tooling-venv/bin/python \
  --humaneval-summary /absolute/original-HumanEval/pilot-summary.json
```

该入口只支持固定三题，先完成控制，再运行外部 CLI、导入、验收、解析和报告，完成即 STOP。
Claude Code 仍为关闭配置项；没有新框架、产品依赖升级、数据库/服务变化或真实产品运行入口。

已保存证据的纯离线复核（不运行模型、候选代码、Docker 或 Verifier）：

```bash
uv run --locked python -m scripts.swe_external_report replay \
  --output /home/dev/.local/state/samescale-eval/swe-external-pilot-20261014 \
  --trusted /home/dev/.local/state/samescale-eval/swe-external-verifiers-20261014-v8 \
  --humaneval-summary /home/dev/.local/state/samescale-eval/pilot-20261014-v3/pilot-summary.json
```

可以将包解压到新的私有目录，用 `tar --same-permissions` 保留清单中的权限，再改上述三个
参数；记录中原路径作为原始元数据保留。重建镜像会生成
新的本地内容 ID，需新控制/新 TaskStore 绑定，不能偷偷更新已有授权或验收收据。离线回放
只核对已有材料，不能当作新验收；镜像及工具缓存不在原始包中，重新执行需要固定镜像下载。

原始事件、全部最终源代码、隐藏资产、八代准备失败/控制日志、三份 intake/验收/export、
执行时原始脚本及最终协议源快照存于仓库外单独存储。Git 仅有脚本、配置、此表和小摘要。
[存储清单与 SHA-256](artifact-receipt.json)。HumanEval/此前预检包保持原字节。
许可沿用各基线项目 BSD/MIT/Apache 及嵌入软件通知；Verified card 无单独显式许可标签，
不冒称全部 JSON/镜像均获 SameScale 的 Apache 许可，也未公开重分发原始完整数据包。

本地 focused 测试 17 PASS，Ruff/格式/mypy PASS；三个导出回放、两个逐字节摘要回放与清单
核对 PASS，隐藏测试仍只在 Verifier 中。远端 CI 与本地结果分开报告。**已停止等待全量确认**。
