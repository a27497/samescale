# SWE Verifier 测试充分性 Canary

本脚本只在 Git 外的工作副本中变异已经通过独立验收的最终代码，并使用原有
`PinnedVerifierSandbox` 重跑相同 Verifier。它不启动 Agent、Codex CLI、Judge 或付费 API，
不接入产品运行流程，也不修改 REAL_CODEX 门禁或原收据。README 的已知限制和数字不变。

## 固定方法

来源是 [2026-10-14 固定全量报告](evidence/swe-full-20261014/report.json)，脚本校验其 SHA256。
选择 `group=SWE-bench AND environment=PASS AND verifier=PASS` 的全部18题，保持报告顺序；
排除原先失败2题、启动前环境失败5题及 HumanEval。前5题先作试点，其余13题只能在试点
流程通过后运行。选择不依赖此次变异结果，不补题、不重跑 Agent。

[预先固定的18条注入规则](../evaluation/canary/swe-repair-regressions.json) 属于一类
`SINGLE_REPAIR_REGRESSION`：撤回或改坏一处修复相关的生产代码，包括分支保护、返回值、
优先级和输出格式。每题一个变异，不作随机挑选，也不根据结果改选变异。每条规则明确文件、
唯一匹配的原文、替换文和行为理由；生产文件先由原 `base.tar` 加已验收 `solution.patch`
重建，再作一次替换及 Python 语法解析。只有目标生产文件的 diff 被重新生成；其他补丁块
逐字保留，尤其不删除或削弱 Agent 添加的测试。原 Verifier 的上游隐藏测试恢复逻辑不变。

每题分别运行原交付副本（control）和注入副本（mutant），二者使用原收据绑定的 task digest、
Verifier digest、镜像内容 ID、测试命令、必需 F2P/P2P 检查集合及原30秒上限。镜像必须已存在，
不拉取或构建。沙箱沿用只读 rootfs/工作区、无网络、无凭据、UID10001、128MiB、0.5CPU、64 PID；
隐藏资产仍为独立 `/verifier` 挂载。被验代码只在隔离容器执行，宿主只解析语法和应用文本补丁。

判定：

| 前提/观察 | 结论 |
| --- | --- |
| control PASS，mutant 完整验收 FAIL | `DETECTED`：检出本次注入 |
| control PASS，mutant 完整验收 PASS | `SURVIVED`：漏检候选；需结合注入的非等价行为见证判断实际漏检 |
| control 非 PASS、超时、缺失/重复/错误检查 ID、零检查、截断、清理失败、输入漂移 | `INCONCLUSIVE`，不得算作检出或漏检 |

完整验收要求报告通过字段、分数和各检查一致，检查 ID 与原集合逐项匹配，容器 exit0，
全部生命周期完成且输入输出工作区 digest 一致。Verifier 进程 exit0 自身不是题目 PASS。
对于 survivor，单独的最小行为见证应对比正确/变异代码并说明违反的公开需求；见证不能
替代或回写原 Verifier 结果，也不能把可能等价的变异直接宣传为测试漏洞。

试点的流程门槛是5个 control 全 PASS、5个 mutant 语法有效且各有完整 PASS/FAIL 结果，
并且原证据清单不变。**不要求5个 mutant 全 FAIL**；漏检正是要记录的结果。
脚本分开 `pilot` / `expansion`，每个阶段先排他写入 started 标记，避免中断后自动重跑。
失败保留所有现存文件；后续纠错需新输出目录并如实说明实际复跑次数。

## 用法

仓库 [开发安装](PRODUCTIZATION.md) 的锁定 Python 环境及 Docker 必须可用：

```bash
uv sync --locked
uv run --locked python -m scripts.swe_verifier_canary --help
```

`--evidence-base` 是已有归档恢复后的共同父目录，其下必须有：

- `swe-full-20261014/`（含新增题的最终交付、base.tar、收据和原 task package）
- `swe-external-pilot-20261014/`（原试跑题的相同资产）
- `swe-external-verifiers-20261014-v8/`（原试跑的精确 Verifier 包）
- `swe-full-20261014-evidence.tar.gz` 和 `swe-external-pilot-20261014-evidence.tar.gz`

参见 [原归档位置/摘要](evidence/swe-full-20261014/archive-receipt.json)。这些文件和镜像不在
Git 中；仅克隆仓库不足以复跑。脚本用收据摘要和包/交付 digest 查找原包，不重新执行准入、
导入记录或修改 TaskStore。传输归档时保留原权限、符号链接和目录；镜像内容 ID 须另行提供。

以下命令从仓库根目录执行；输出必须是**从未存在过**的 Git 外目录，且与原证据互不包含。
请替换路径；本轮实际输出目录和报告由 PR / CURRENT_MILESTONE 指明。

```bash
uv run --locked python -m scripts.swe_verifier_canary prepare \
  --evidence-base /absolute/original/samescale-eval \
  --output /absolute/new/canary-run

uv run --locked python -m scripts.swe_verifier_canary pilot \
  --output /absolute/new/canary-run

# 查看 pilot.json 的 gate_passed 和每题结果。通过后才执行：
uv run --locked python -m scripts.swe_verifier_canary expansion \
  --output /absolute/new/canary-run

# 只读复核，不调用 Docker、模型或网络：
uv run --locked python -m scripts.swe_verifier_canary replay \
  --output /absolute/new/canary-run
```

所有输出保留在外部目录：`plan.json` / `plan-pin.json` 绑定预注册规则、原收据、镜像和输入；
`original-inventory.json` 保存原根目录内全部文件（包括 `.git`、原 inventory 文件）的
SHA256、权限和符号链接文本，以及两个原归档。prepare 前后、各阶段前后和 replay 均复核，
读取可能更新 atime，不以时间戳证明字节变更。`cases/<题号>/` 下保存包副本、`mutation.patch`、
control/mutant 的输入、原始沙箱 artifacts、生命周期、observation 和 result；`pilot.json`
保存扩展前快照，`expansion.json` / `report.json` / `results.csv` 保存完整结果。
replay 重新推导报告并对比保存结果；它是完整性/一致性复核，不是新的验收运行。
当前 replay 引用准备时的原证据绝对路径；跨机器须恢复同路径或重新 prepare 到新目录。

脚本的 `SURVIVED` 只说明同一固定集合未拒绝本次变异。检出率/漏检率限于这18个条件样本、
这类手工选取的单点回归；它不是完整变异测试评分、随机错误概率、SWE-bench 总体覆盖率，
也不能反推原先 PASS 代码在所有需求下正确。原收据及 Agent 自报始终保持原作用域。

## 脚本回归检查

```bash
uv run --locked pytest -q tests/test_swe_verifier_canary.py
uv run --locked ruff check scripts/swe_verifier_canary.py tests/test_swe_verifier_canary.py
uv run --locked ruff format --check scripts/swe_verifier_canary.py tests/test_swe_verifier_canary.py
uv run --locked mypy scripts/swe_verifier_canary.py tests/test_swe_verifier_canary.py
```

这些测试使用离线合成数据，不消耗原题或运行 Docker；已加入现有 Fast CI 的完整分片和
self-hosted 清单，原29项独立指纹及后加的诊断测试仍保留。线上 Canary 不会在 CI 自动运行。

## Survivor 的独立行为见证

补充脚本只接受主 Canary 中已出现 `SURVIVED` 的题。它复制主 Canary 的包与输入，
在**新的补充包**里将 test_command / required IDs 换为操作员审阅过的公开断言脚本，
仍用相同 pinned 镜像、代码重建器和隔离沙箱。原包、主结果和主验收集合不变。
断言失败记为补充 FAIL；非断言异常、缺失检查等仍为 INCONCLUSIVE。补充输出与主结果
分开保存，且同一目录拒绝重复执行；不把补充检查称为原 Verifier 的检查。

仓库提供两个公开行为用例：float16 Quantity 经 `copy=True` 拷贝后仍应保留 dtype；
普通模块的 generated xunit fixture 应在没有 `-v` 时隐藏。第二个用例是相邻的模块路径，
超出原问题中 `unittest.setUpClass` 的具体示例，不声称原示例在注入后失效。
用例只依赖公开 API，不包含隐藏断言源码、参考补丁或已知答案资产：

```bash
uv run --locked python -m scripts.swe_canary_witness \
  --output /absolute/new/canary-run \
  --task-id astropy__astropy-8872 \
  --probe evaluation/canary/astropy_quantity_copy_probe.py

uv run --locked python -m scripts.swe_canary_witness \
  --output /absolute/new/canary-run \
  --task-id pytest-dev__pytest-8399 \
  --probe evaluation/canary/pytest_module_fixture_probe.py
```

补充结果在 `witnesses/<题号>/witness.json`；`control=PASS AND mutant=FAIL` 建立该用例上的
非等价行为，结合主 mutant=PASS 才确认这次实际漏检。`probe.py`、包摘要、各模式的沙箱
原始结果和输入都在该独立目录保留。添加其它用例时传入新的、已审阅的 Python 断言文件；
脚本不猜测用例，也不启动模型。普通 `replay` 只复核主 Canary；补充 witness 由外部产物
清单摘要和保存的 observation/result 单独复核，不声称主 replay 已复核补充验收。
