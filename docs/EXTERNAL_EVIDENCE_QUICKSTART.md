# 首次私有接入：已保存 Codex 证据

本路径只读取**人工批准的单条记录和最终 Workspace**。不启动 Codex、Agent 或
Verifier，不访问开发登录目录，不接管订阅。REAL_CODEX 保持关闭。
支持格式、权利/隐私边界和容量见 [接口契约](EXTERNAL_CODEX_EVIDENCE.md)。
本轮历史 Hook 5/5 是功能回归；没有新获批开发记录，`FRESH_CASE_PENDING` 保留。

## 1. 独立安装和隔离启动条件

需要 Git、锁定版本兼容的 uv/Python、Node/npm，以及本地 Docker Compose/PostgreSQL。
不要在有未提交修改的 checkout 操作，也不要沿用正式服务的 `.env`、数据库或端口。
以下 Bash 命令从新 checkout 的仓库根执行。先用 `ss -ltn` 确认示例端口未占用；若被占用，
换两个端口。选择全新 Compose 项目名，先用 `docker compose ls` 确认未存在。
这些命令需要包含 P1 修复的版本：PR 尚未合并时，clone 后先
`git switch codex/external-evidence-p1-20261011`（跟踪同名远端分支）；合并后使用已验收 main。

```bash
git clone https://github.com/a27497/samescale.git samescale-private
cd samescale-private
uv sync --locked
npm ci --prefix frontend --no-audit --no-fund
npm run build --prefix frontend
umask 077
export SS_PRIVATE="$(mktemp -d /tmp/samescale-private.XXXXXX)"
export SS_PROJECT="samescale-private-$(date +%s)-$$"
export POSTGRES_PORT=58691
export SS_API_PORT=58690
export POSTGRES_USER=harnesslab
export POSTGRES_DB=harnesslab
export POSTGRES_PASSWORD=harnesslab_isolated_local_only
export DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB"
export HARNESSLAB_ENVIRONMENT=test
# 只创建全新项目的 postgres；不启动既有服务、migrate/API 容器或 Agent。
docker compose -p "$SS_PROJECT" up -d --wait postgres
uv run --locked alembic upgrade head
mkdir -m 700 "$SS_PRIVATE/records" "$SS_PRIVATE/empty-artifacts"
export HARNESSLAB_WORKBENCH_DIST="$PWD/frontend/dist"
export HARNESSLAB_WORKBENCH_ARTIFACT_ROOTS="[\"$SS_PRIVATE/empty-artifacts\"]"
export HARNESSLAB_EXTERNAL_EVIDENCE_POLICY="$SS_PRIVATE/evidence-policy.json"
export HARNESSLAB_ENABLE_REAL_CODEX=false
# 新的私有产品操作员口令，至少 32 字符；不用开发 CLI/API 登录凭据。
read -rsp 'New local operator passphrase (32+ characters): ' HARNESSLAB_LOCAL_CONFIGURATION_TOKEN
export HARNESSLAB_LOCAL_CONFIGURATION_TOKEN
```

标准 `docker-compose.yml` API 服务目前**不传递**证据策略/操作员环境变量，也**不挂载**
批准来源；直接 `compose up` 不提供该接入路径。这里仅用 Compose 创建独立数据库，
在 host 启动私有 API。它不是新的容器发行能力或公网入口。外部记录本身没有 DB schema
变更；上面的迁移仅初始化全新产品测试数据库。不要对既有数据库执行它。

## 2. 创建空策略、检查权限

```bash
.venv/bin/python - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ['SS_PRIVATE'])
p = Path(os.environ['HARNESSLAB_EXTERNAL_EVIDENCE_POLICY'])
p.write_text(json.dumps({'schema_version': 1, 'store': str(root / 'records'), 'sources': []}))
p.chmod(0o600)
PY
uv run --locked harnesslab external-evidence check
```

期望 `NO_APPROVED_SOURCES`，不是故障，也不代表任务通过。策略必须为操作员所有的独立
普通文件（0600）、存储目录为 0700；禁止链接、硬链接、凭据目录、来源/Workspace/存储
互相重叠。只读检查仅检查策略和目录元数据，不读取来源内容、不验证 pin、记录或任务，
不写存储、不执行 Agent/Verifier。异常退出码 2，配置可用（包括空来源）为 0；JSON 中不
返回路径、口令或异常文本。`operator_configured` 仅表示口令长度，不认证输入者。

## 3. 人工审查并固定摘要

逐项核对来源身份、保存方式和最终 Workspace 的配对。由人审查文本及文件名中的私人信息、
凭据、原始会话、隐藏 verifier/oracle 和第三方权利。不要扫描 `~/.codex`，不要把私有 rollout
当作公开 `exec --json`。自动敏感模式拒绝**不能代替人工审查**。已经获准的专用目录可用：

- `codex-jsonl-v1`：目录只含用户已经保存的 `events.jsonl`，不是交互会话目录；
- `native-hook-v1`：已保存的内容为空/已脱敏 Hook spool；
- `verified-hook-v1`：既有完整且脱敏的严格绑定 Hook bundle；
- `codex-h-lane-v1`：既有完整 H-Lane 材料。

最终 Workspace 只支持非空 UTF-8 普通源文件，最多 500 文件/4 MB，无 `.git`、`.env*`、
认证文件、verifier/oracle 或二进制。必须明确缺失内容；不要为了导入成功删掉工程再声称完整。
为审查后的副本计算 pin，并**另存到策略以外**的可信审查记录中：

```bash
# 仅设置已经逐项批准的独立目录，不能指向认证或会话发现目录。
export SS_SOURCE=/absolute/reviewed/one-source
export SS_WORKSPACE=/absolute/reviewed/final-workspace
export SS_FORMAT=codex-jsonl-v1
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from harnesslab.tasks.package import digest_tree, sha256_bytes
source = Path(os.environ['SS_SOURCE'])
print('source:', sha256_bytes((source / 'bundle.json').read_bytes())
      if os.environ['SS_FORMAT'] == 'verified-hook-v1' else digest_tree(source))
print('workspace:', digest_tree(Path(os.environ['SS_WORKSPACE'])))
PY
```

Hash 不是来源真实性证明。不要信任不可信 manifest 的自报 pin；不要在摘要不匹配后盲目重算
覆盖批准值。后续的任何内容修改都需要重新人工审查和独立批准。没有可靠任务/Verifier 时
保持 NOT_VERIFIED；本 Quickstart 没有 `verify-workspace` 或任何执行授权。

可选的**已获批历史回归**：来源是当前 checkout 的
`docs/evidence/real-codex-native-hook-20261007/frozen/attempt-1`，Workspace 为其
`final-workspace`。使用 `verified-hook-v1`、`historical`，先比对既有批准值：

- source：`sha256:17243ac021add7d99478366ce0d843dae1a9d95a218e53f716a7ef538b86aa23`
- Workspace：`sha256:760feb0c05137db5266f8aa0b9c9684478228cf66755c3c6bfe6a09f5889ffc8`

它读取历史独立 5/5，不重跑历史 Verifier；原 Episode 是 `unverified / NOT_VERIFIED`。
历史和 `synthetic` 夹具不能充当新的真实开发案例，普通提供的未知来源用 `unverified`。

## 4. 明确批准策略中的一条来源

在 Bash 设置经审查固定的值，然后写入策略。**不要直接复制占位摘要**。

```bash
export SS_SOURCE_ID=reviewed-saved-run-001
export SS_KIND=unverified
export SS_SOURCE_PIN=sha256:EXTERNALLY_RETAINED_REVIEWED_SOURCE_PIN
export SS_WORKSPACE_PIN=sha256:EXTERNALLY_RETAINED_REVIEWED_WORKSPACE_PIN
.venv/bin/python - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['HARNESSLAB_EXTERNAL_EVIDENCE_POLICY'])
policy = json.loads(p.read_text())
policy['sources'] = [{
    'source_id': os.environ['SS_SOURCE_ID'], 'format': os.environ['SS_FORMAT'],
    'source_kind': os.environ['SS_KIND'], 'path': os.environ['SS_SOURCE'],
    'digest': os.environ['SS_SOURCE_PIN'], 'workspace': os.environ['SS_WORKSPACE'],
    'workspace_digest': os.environ['SS_WORKSPACE_PIN'],
}]
p.write_text(json.dumps(policy, indent=2)); p.chmod(0o600)
PY
uv run --locked harnesslab external-evidence check
uv run --locked harnesslab serve --host 127.0.0.1 --port "$SS_API_PORT"
```

CLI/API 仅使用这个显式策略；不自动发现来源。浏览器访问
`http://127.0.0.1:58690/external-runs`（按实际端口调整），输入新的本地操作员口令 →
解锁 → 选择来源 → 勾选接入同意 → 导入。口令仅在页面内存，关闭页面清除，不是 Codex Token。
检查原 Episode、独立 Workspace 验收、来源类别、PARTIAL/缺失字段、UNKNOWN 工具退出、
NOT_ATTESTED 来源声明。导入成功/工具成功不意味着任务通过。

## 5. 导出，两次离线复核

点击导出按钮，另存页面显示的 `X-Evidence-SHA256` pin。导出不含原始会话、口令、隐藏
Verifier 或原始日志。终端指定新输出文件，各执行一次：

```bash
export SS_EXPORT=/absolute/downloaded/saved-evidence.json
export SS_EXPORT_PIN=sha256:EXTERNALLY_RETAINED_EXPORT_PIN
PYTHONPATH=src:. .venv/bin/python scripts/replay_external_evidence.py \
  --evidence "$SS_EXPORT" --sha256 "$SS_EXPORT_PIN" --output "$SS_PRIVATE/replay-a.json"
PYTHONPATH=src:. .venv/bin/python scripts/replay_external_evidence.py \
  --evidence "$SS_EXPORT" --sha256 "$SS_EXPORT_PIN" --output "$SS_PRIVATE/replay-b.json"
cmp "$SS_PRIVATE/replay-a.json" "$SS_PRIVATE/replay-b.json"
```

带 audit guard 的脚本拒绝进程执行和网络；复核记录身份、Workspace 与已有验收摘要，
不运行 Agent/Verifier、不重建丢失材料、不认证来源，也不构成新的独立验收。

## 错误处理与收尾

| 状态/安全代码 | 最小操作 |
| --- | --- |
| `EXTERNAL_EVIDENCE_DISABLED` | 尚未设置策略；设置 host 环境变量后重启私有 API |
| `EVIDENCE_POLICY_PERMISSION` | 核对策略归属/0600，不能使用认证文件 |
| `EVIDENCE_POLICY_INVALID` | 核对 JSON、canonical 路径、分离目录和摘要格式 |
| `NO_APPROVED_SOURCES` | 操作员审查、脱敏并逐项批准；不会自动发现会话 |
| `SOURCE_LOCATION_UNAVAILABLE` | 核对明确批准的目录是否存在/可访问；不读取其他来源 |
| `LOCAL_OPERATOR_REQUIRED` / `LOCAL_CONFIGURATION_DISABLED` | 核对本地口令/至少 32 字符及 host 配置 |
| `EVIDENCE_PIN_MISMATCH` | 停止接入，比对可信审查记录；禁止盲目更新 pin |
| `EVIDENCE_SENSITIVE_INPUT` | 拒绝接入；人工审查脱敏后重新明确批准 |
| `EVIDENCE_INPUT_UNSUPPORTED` / `EVIDENCE_IMPORT_REJECTED` | 核对格式、结构与容量；不补造替代结果 |
| `EVIDENCE_RECORD_CORRUPT` / `EVIDENCE_INTEGRITY_ERROR` | 保留身份和损坏事实；详情/验收/导出拒绝，健康记录继续可读 |
| `EVIDENCE_STORAGE_UNSAFE` | 全局拒绝；核对权限、链接、结构和容量，不能当作单条损坏忽略 |

没有自动修复/重试/重新执行；操作者需处理损坏材料，保留审计证据。重启不会修复损坏。
原来源已移除时，页面会提示位置不可用，但已保存的健康记录仍可读取；不补采原会话。
先 Ctrl-C 停止**本次** host API，然后仅清理刚创建的独立 Compose 项目：

```bash
docker compose -p "$SS_PROJECT" down --volumes
```

不要对其他项目执行清理。私有证据目录/导出由用户决定留存，不自动上传或删除。
后续新的实际记录仍需独立来源批准；订阅认证、SIWC 和真实执行资格不在此路径内。
