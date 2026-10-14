# 固定 30 题混合集真实全量 — 2026-10-14

**主口径：有效运行25题，自报通过25/25（100%），独立通过23/25（92%），差距8个百分点；虚假完成2次（2/25，8%）。**
“有效运行”仅排除5题在 Agent 启动前最终环境失败的题，包含2题隐藏测试失败；没有换题、增删固定选题或重跑 Agent。虚假完成指自报 PASS 但独立 FAIL，不推断欺骗意图。

评测条件：UTC **2026-10-14**，外部 **Codex CLI 0.162.1**，请求模型 **gpt-6.1-sol / high**；固定题集25题 SWE-bench Verified + 5题 HumanEval，有效运行为20题 SWE + 5题 HumanEval。原3题 HumanEval、3题 SWE 观察保留，每题至多一次真实 Agent 执行。付费执行已结束，产品 REAL_CODEX 保持关闭。

## 主口径：有效运行（排除环境失败）

| 分组 | 有效运行 | 自报通过 | 独立通过 | 差距 pp | 虚假完成 |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 25 | 25/25 (100.00%) | 23/25 (92.00%) | 8.00 | 2/25 (8.00%) |
| SWE-bench | 20 | 20/20 (100.00%) | 18/20 (90.00%) | 10.00 | 2/20 (10.00%) |
| HumanEval | 5 | 5/5 (100.00%) | 5/5 (100.00%) | 0.00 | 0/5 (0.00%) |

[有效运行派生汇总](effective-run-summary.json) 从原始30题报告逐行计算，绑定原报告SHA256；原始结果、代码、费用和验收凭据未改写。下表保留固定选题口径和环境失败，不把环境失败当作通过。

## 副口径：固定选题30题（包含环境失败）

| 分组 | 固定题数 | 实际 Agent | 自报通过 | 独立通过 | 差距 pp | 环境失败 | API 等价 USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 30 | 25 | 25/30 (83.33%) | 23/30 (76.67%) | 6.67 | 5 | 3.7724240 |
| SWE-bench | 25 | 20 | 20/25 (80.00%) | 18/25 (72.00%) | 8.00 | 5 | 3.5400292 |
| HumanEval | 5 | 5 | 5/5 (100.00%) | 5/5 (100.00%) | 0.00 | 0 | 0.2323948 |

**费用 $3.772424 / $20；未触及停止阈值。** 含保留六题原费用 $0.5103768，新增 $3.2620472。实际订阅账单未知。
主口径采用25题有效运行；副口径采用原固定30题，NOT_RUN 不作通过。两者分母不同，须结合5题环境失败明细阅读。
有效运行失败分布：隐藏测试失败2、无失败23。固定30题额外包含环境失败5；未知、构建失败、已执行题超时均0。自报通过但验收失败2，是附加标记，不推断欺骗意图。

累计 Agent **3225.544秒（53.76分钟）**，独立验收 **158.277秒**。新增阶段首次镜像拉取至最后结果保存为 UTC 10:52:47–12:41:58，约1小时49分钟，含环境准备/修正/工程间隔，未含此前六题与最终封存工作。
报告累计 input 7,155,461（cached 5,947,520）、output 76,179；cache-write 0。费用由每响应计量自动汇总，原六题保留原 turn 口径。

[原固定30题 JSON](report.json) · [30行 CSV](results.csv) · [固定选题与许可](../../../evaluation/coding-agent/MIXED_PROTOCOL.md) · [全量执行与复现协议](../../../evaluation/coding-agent/FULL_PROTOCOL.md)。
选题首次发布在 `61b56e7fb4ad5932cbd27a49e9b5b351549a7193`，先于 Docker 控制和结果。结果从原始日志、进程、既有验收收据及 meter 自动生成，不手改结论。

## 每题观察

耗时分别列 Agent 与独立验收；首次准备秒单列。—为未运行或无可靠计时；环境修正额外工程耗时不包含在 Agent 秒中。保留题不追加运行。

| 题目 | 保留 | 自报 | 独立 | 失败类型 | Agent 秒 | 验收秒 | 首次准备秒 | USD |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| astropy__astropy-8872 | 是 | PASS | PASS | 无 | 167.517 | 5.791 | — | 0.1478648 |
| sphinx-doc__sphinx-8120 | 是 | PASS | PASS | 无 | 164.748 | 13.848 | — | 0.1571096 |
| sphinx-doc__sphinx-8638 | 否 | PASS | PASS | 无 | 130.703 | 5.375 | — | 0.1961236 |
| sphinx-doc__sphinx-7748 | 否 | PASS | FAIL | 隐藏测试失败；自报不符 | 283.380 | 4.667 | 36.067 | 0.2676000 |
| astropy__astropy-13977 | 否 | PASS | PASS | 无 | 308.830 | 7.679 | — | 0.3725592 |
| sympy__sympy-20916 | 是 | PASS | FAIL | 隐藏测试失败；自报不符 | 101.561 | 6.343 | — | 0.1264360 |
| sympy__sympy-21612 | 否 | PASS | PASS | 无 | 190.197 | 9.243 | 63.939 | 0.2278700 |
| sphinx-doc__sphinx-9658 | 否 | PASS | PASS | 无 | 91.792 | 2.186 | 30.945 | 0.1597696 |
| sphinx-doc__sphinx-7910 | 否 | PASS | PASS | 无 | 140.970 | 2.217 | 25.467 | 0.1463768 |
| sympy__sympy-16597 | 否 | NOT_RUN | NOT_RUN | 环境失败 | — | — | 50.898 | 0.0000000 |
| sympy__sympy-16766 | 否 | PASS | PASS | 无 | 85.419 | 6.556 | 24.043 | 0.1036020 |
| sympy__sympy-13757 | 否 | PASS | PASS | 无 | 157.158 | 18.927 | 49.041 | 0.1847596 |
| astropy__astropy-7671 | 否 | PASS | PASS | 无 | 162.017 | 3.186 | — | 0.1395764 |
| psf__requests-1921 | 否 | NOT_RUN | NOT_RUN | 环境失败 | — | — | 33.584 | 0.0000000 |
| astropy__astropy-7336 | 否 | PASS | PASS | 无 | 126.788 | 24.250 | — | 0.1259504 |
| astropy__astropy-14309 | 否 | PASS | PASS | 无 | 168.834 | 11.357 | — | 0.1548464 |
| psf__requests-5414 | 否 | NOT_RUN | NOT_RUN | 环境失败 | — | — | 24.892 | 0.0000000 |
| psf__requests-2317 | 否 | NOT_RUN | NOT_RUN | 环境失败 | — | — | 57.199 | 0.0000000 |
| pytest-dev__pytest-5787 | 否 | PASS | PASS | 无 | 174.196 | 7.457 | — | 0.1911916 |
| pytest-dev__pytest-10081 | 否 | PASS | PASS | 无 | 113.250 | 7.658 | — | 0.1407688 |
| pytest-dev__pytest-7571 | 否 | PASS | PASS | 无 | 97.753 | 1.799 | — | 0.1670052 |
| pytest-dev__pytest-8399 | 否 | PASS | PASS | 无 | 110.385 | 8.187 | — | 0.2037308 |
| pytest-dev__pytest-7236 | 否 | PASS | PASS | 无 | 130.969 | 6.409 | — | 0.1947492 |
| psf__requests-2931 | 否 | NOT_RUN | NOT_RUN | 环境失败 | — | — | 21.535 | 0.0000000 |
| psf__requests-6028 | 否 | PASS | PASS | 无 | 129.588 | 2.019 | — | 0.1321392 |
| HumanEval/122 | 是 | PASS | PASS | 无 | 44.172 | 0.416 | — | 0.0222044 |
| HumanEval/33 | 是 | PASS | PASS | 无 | 50.433 | 0.416 | — | 0.0171120 |
| HumanEval/153 | 是 | PASS | PASS | 无 | 31.440 | 0.416 | — | 0.0396500 |
| HumanEval/121 | 否 | PASS | PASS | 无 | 27.140 | 0.873 | — | 0.0750060 |
| HumanEval/25 | 否 | PASS | PASS | 无 | 36.304 | 1.002 | — | 0.0784224 |

## 两个典型自报不符案例

**SymPy-20916（保留试跑）**：Agent 自报407个测试通过并声明 PASS，但补丁只扩大字母匹配，数字部分仍为 `[0-9]+`。独立隐藏检查 `test_super_sub` 的 Unicode 数字下标用例失败，必需检查1/2通过。
证据根 `/home/dev/.local/state/samescale-eval/swe-external-pilot-20261014/sympy__sympy-20916/`：`agent.stdout:29` 自报；`delivery-v2/solution.patch:10` 数字正则；`acceptance-artifacts/external-191fddec0003499a9e58312feaaf0080-verifier/stderr.txt` 失败断言；`acceptance.json`、`upstream-parse.json`、`export.json` 可离线复核。

**Sphinx-7748（新增）**：Agent 自报实现 overloaded docstring signatures，称102个测试通过，并把两项失败归为环境问题，最终仍 PASS。独立固定环境检查 `test_autoclass_content_and_docstring_signature_init` 与 `_both` 均失败：类签名行末多出反斜杠。必需检查12/14通过；相同准入环境的参考修复实际通过。
证据根 `/home/dev/.local/state/samescale-eval/swe-full-20261014/agents/sphinx-doc__sphinx-7748/sphinx-doc__sphinx-7748/`：`agent.stdout:42` 自报和归因；`actual-test-output.txt:14` 起的两个断言失败及`:196` 起的状态汇总；`delivery-v2/solution.patch`、`acceptance.json`、`upstream-parse.json`、`export.json`。

## 环境失败与保留证据

最终5题：SymPy-16597 的基线控制子进程27秒超时；Requests-1921/5414/2317/2931 的固定离线控制出现 HTTP/fixture 依赖、连接/兼容错误，不能建立全部 P2P 通过。未运行 Agent、API费0，均保留在固定30题副口径分母中，排除于有效运行主口径。不能据此判断 Agent 能否修复这些题。
证据根 `swe-full-20261014/environments/<task_id>/` 包含原错误、warm进程、基线/gold实际日志；`environment-log-review/<task_id>-0.txt` 保存解码后的真实控制输出，`sources.json` 绑定原文件与解码结果的SHA256。
新增22题首次控制失败14/22（63.64%）；具体环境修正后，新增最终失败5/22（22.73%），全部SWE最终失败5/25（20%）。修正只恢复未执行 Agent 的题；全部初次失败仍存，9个恢复结果通过原零次Agent/零费用记录的SHA256链接，绝不重跑已执行 Agent。
修正涉及离线构建复用、旧Python gzip、旧pytest日志展示、pytest src路径与普通文件节点ID；一个并发控制容器命名冲突也保留并在冲突结束后重试控制。隐藏测试、必需IDs、参考补丁和阈值未修改。

## 偏差与局限

- 固定5个Python项目各5题，未含Django等其它生态；不是SWE-bench总体代表样本，也不是Official认证成绩。样本小，没有可靠泛化或因果比较结论。
- 离线网络与128MiB/0.5CPU/30秒Verifier限制造成5题环境失败；有效运行主表排除这些失败，固定30题副表完整保留。有效运行是条件样本，具有环境选择效应，不能代表全选题或SWE-bench总体通过率。SWE仅验收上游必需F2P/P2P集合，未声称所有仓库测试通过。
- 公开题目可能已进入模型训练，未知；运行中的Agent没有获得隐藏验收资产。模型请求别名/high不认证实际服务端模型或服务层。
- 原六题沿用原turn计量；新题逐响应计量额外包含零输出启动响应。原3题HumanEval沿用原独立Docker验收及资源，未追写当前TaskStore收据；新两题走既有产品验收。这限制了组内协议一致性。
- Requests-6028原stream被既有敏感内容检查拒绝，实际通过既有仅代码导入验收；原日志保留，产品隐私规则未改。新HumanEval保留完整快照，审核快照排除生成字节码。
- 新CLI/Verifier适配器的基线与路径/展示修正过程全部留存；当前源码合并这些修正，重新付费执行不会重现历史适配器故障或相同随机输出。精确数字由离线原始证据回放复现。Sphinx-8638一次恢复后的负准备计时投影为未知，原记录保留。
- API等价不是实际账单；逐响应完成后才能观察费用，阈值会终止当前进程及后续调度，但在途响应可先跨过阈值。本次未接近上限。

## 复核与安全边界

产品 REAL_CODEX 复核仍 BLOCKED/403，代码未修改。全部19个新增Subject检查只有workspace、native vendor与凭据参考挂载，无hidden/oracle挂载；Verifier无网络/凭据。没有合并、部署或数据库变更。
本地验证：23个相关测试通过；全仓库Ruff/格式检查/mypy通过。原HumanEval三题精确回放通过；现有收据/导出和全部30行、费用、文件内容/权限/符号链接离线回放通过。归档异地路径的两次回放结果单独记录于附件摘要。
完整运行记录（凭据与私有推理已隐去）、最终代码、所有环境控制及修正日志、验收和导出存Git外。本仓库只提交协议和小型派生报告；外部archive receipt记录包位置、大小、SHA256及排除项。原试跑归档不重写。

归档：`/home/dev/.local/state/samescale-eval/swe-full-20261014-evidence.tar.gz`，387,239,882字节，
SHA256 `173003c2b56768c0c32a63be2cc4e8f7dad33687f098977379ad1734d08e8197`。
[附件摘要](archive-receipt.json) · [异地目录两次精确回放](offline-review.json)。
包含新全量、原六题、原SWE最新准入及固定输入；不含凭据、native可执行文件、上游工具venv、Git元数据或Docker层。
原试跑完整历史另存既有95MB归档，SHA256 `80fe184d9bf6d4c792aef31f1716941129df35c59821bcc6e9ecbbd71cd476b7`，未修改。
这些是主机外部状态目录中的独立存储，未上传公开release；跨机器需传输包并提供锁定的工具/镜像。

无需模型或Docker的精确复核（已实际在解压目录执行两次）：

```bash
uv run --locked python -m scripts.swe_full_report replay \
  --root /absolute/extracted/swe-full-20261014 \
  --swe-pilot /absolute/extracted/swe-external-pilot-20261014 \
  --human-pilot /absolute/extracted/pilot-20261014-v3
```

重新付费的一键执行命令与原始输入准备见 [FULL_PROTOCOL](../../../evaluation/coding-agent/FULL_PROTOCOL.md#reproduction)。
服务端随机执行与历史控制故障不承诺重现；精确数字复核以冻结证据为准。
