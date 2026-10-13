# GCP QA 自动部署与回滚

目标是现有 `samescale-grok-qa` 环境，仅更新 `api` 与单次 `migrate`。
服务器：`34.81.153.182`；现有配置：
`/home/dev/.local/state/samescale-grok-qa-20261009/compose.yml`；
网关健康检查：`http://127.0.0.1:18580/api/health`。
不重启 PostgreSQL、gateway，不改变 tunnel、防火墙、其他项目、数据卷或旧镜像。

## 自动流程

1. main 的 Fast CI 或 Offline Regression 完成后触发
   [部署 workflow](../.github/workflows/deploy-gcp.yml)。
2. 先执行离线部署契约测试，再检查**同一 commit、main push 的两个 CI workflow**。
   必须是各自最新 run 的最新 attempt：所有要求的 job 实际成功，无缺失、跳过、失败或取消。
   PR/fork 的结果、旧 commit 的通过记录不能授权部署。手动 Full Release 不属于这两个自动 gate。
3. 通过 `samescale-grok-qa` environment；等待环境保护后重新确认 main 和 CI。
   只部署当前 main：更新中的 main、较旧或已失去 CI 通过状态的 commit 会停止/跳过。
4. GitHub 使用专用密钥登录受限的 `deploy` 用户，只能发出 `deploy FULL_40_CHARACTER_SHA`。
   不提供 shell、SFTP/SCP、端口/Agent 转发、管理员回滚/演练选项或通用 sudo。
5. 服务器固定入口再次检查 main/CI，从单独的 root-owned bare repo 导出精确 commit，使用
   `docker/product/Dockerfile` 本机构建；`SOURCE_REVISION` 必须等于请求 SHA。
   镜像身份使用本机不可变 image ID；保留旧镜像，不执行 prune/rmi。
6. 单次运行 `migrate` 的 `alembic upgrade head`，带 `--no-deps`；此时旧 API 仍运行。
   迁移失败不替换 API 或正式 Compose 配置，不执行数据库 downgrade。
7. 仅停止/删除旧 **api 容器**并用新镜像启动 `api --no-deps`。其他容器不重启。
   当前 nginx 固定解析 API 地址，因此先释放原 API 地址，再检查新 API 是否使用相同地址；
   地址或镜像不一致立即回滚，不通过修改 gateway 掩盖问题。
8. 经现有 gateway 检查 HTTP/JSON：`status=ok` 且 `database=ok` 才记录成功，并保存上一镜像。
   检查失败恢复上一镜像、确认其健康；本次部署仍返回失败，不能把回滚成功算作部署成功。

GitHub concurrency 不取消正在执行的部署；服务器 `flock` 也拒绝第二个并发操作。
同一已部署 commit 的重复成功事件只确认健康，不重复替换 API。SSH 断开不会主动中止服务器
部署；中断记录保留在 root-only 状态目录，下次操作先恢复原镜像。不承诺零停机。

[GitHub workflow_run 规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
要求 workflow 已在默认分支：这个 PR 未合并时，自动部署不会运行。
PR 上仅运行无 SSH/凭据/真实 Docker 的部署契约测试；没有 `workflow_dispatch` 手动部署入口。

## 服务器安装与权限

管理员在审查过的独立 checkout 安装固定入口，部署过程**不会自动安装检出的 ops 脚本**：

```bash
sudo sh ops/gcp/install.sh /absolute/path/to/dedicated-deployment-key.pub
```

安装文件：

- `/usr/local/sbin/samescale-deploy`：清空调用者环境，以隔离 Python 路径运行固定控制器。
- `/usr/local/lib/samescale-deploy/`：root-owned 代码；deploy 无写权限。
- `/home/deploy/.ssh/authorized_keys`：root-owned，专用公钥带 `restrict` 与 forced command。
- `/etc/sudoers.d/samescale-deploy`：仅允许固定控制器及一个小写 40 位 SHA 参数。
- `/var/lib/samescale-deploy/`：0700/root，保存部署锁、构建源码、私有日志和回滚收据。

deploy 不加入 Docker、dev 或普通 sudo 组，不能读取 api.env/数据库配置，也不能改授权文件。
安装器拒绝覆盖不属于本工具的既有 deploy 账户。更改部署控制器后需管理员重新审查并安装。
SSH 服务/防火墙不用修改。

## 你需要配置的 GitHub environment

在仓库 Settings → Environments 创建 **`samescale-grok-qa`**：

- Deployment branches 使用 **Selected branches and tags**，只允许分支 `main`，不允许 tags。
- 如果要求完全自动，不设置 Required reviewers 或等待计时器。若人为增加审批，workflow 会
  等待，审批结束后再次核对 main/CI；Environment 不替代服务器授权检查。
- 添加 environment variable：`DEPLOY_HOST=34.81.153.182`。
- 添加下面两个 **environment secrets**，不要作为仓库文件保存。

| Secret | 值与取得方式 |
| --- | --- |
| `DEPLOY_SSH_PRIVATE_KEY` | 本轮专用 Ed25519 私钥文件的完整内容，从服务器 `/home/dev/.local/state/samescale-deploy-20261013/github_ed25519` 经受信任的 dev SSH/SCP 下载后直接导入。文件为 0600，私钥未打印、未提交。 |
| `DEPLOY_SSH_KNOWN_HOSTS` | 服务器同目录 `github_known_hosts` 文件内容，来自服务器现有 Ed25519 **公钥**，不是临时盲信 ssh-keyscan 结果。固定主机指纹见本轮交付记录。 |

在你自己的电脑执行（`samescale` 是你已有的 dev SSH 别名）：

```bash
umask 077
scp samescale:/home/dev/.local/state/samescale-deploy-20261013/github_ed25519 ./samescale-deploy-key
scp samescale:/home/dev/.local/state/samescale-deploy-20261013/github_known_hosts ./samescale-deploy-hosts
gh secret set DEPLOY_SSH_PRIVATE_KEY --repo a27497/samescale --env samescale-grok-qa < ./samescale-deploy-key
gh secret set DEPLOY_SSH_KNOWN_HOSTS --repo a27497/samescale --env samescale-grok-qa < ./samescale-deploy-hosts
```

命令通过文件 stdin 读值，不把私钥放入参数或终端日志。文件留存/删除由你决定，不提交。
`api.env`、数据库密码与 Compose 私有配置只留在服务器，不进入 GitHub Secrets 或构建上下文。
SSH 私钥只用于 runner 临时文件，结束时删除；严格检查服务端 host key，不启用 Agent 转发。
服务器复核 CI 使用 job 自带的**临时只读 GitHub token**，经 SSH stdin 传入，只在内存中使用；
不加入镜像、命令参数、环境转发或日志。管理员本地演练不传 token 时用公开 API，限流则失败关闭。
本轮不创建/填写 GitHub environment、Secrets 或变量，等待用户配置；不会合并 PR 或主动触发部署。

## 状态、日志与手动回滚

在服务器 dev 会话中，仅查看不含密码的收据与状态：

```bash
sudo cat /var/lib/samescale-deploy/last-success.json
curl --fail http://127.0.0.1:18580/api/health
```

成功记录含当前/上一 image ID、源 SHA 与 root-only Compose 快照位置。原有
`compose.yml.bak-314fe71c-20261013` 和 `rollback-image-314fe71c.txt` 不覆盖、不删除。
原始构建/迁移输出可能含敏感内容，仅写入 `/var/lib/samescale-deploy/runs/<id>/private.log`
（0600/root）；不要复制到公开 issue、CI 或 PR。`events.log` 是不含环境值的操作阶段摘要。

管理员回滚上一成功镜像（deploy 密钥不允许请求此命令）：

```bash
sudo /usr/local/sbin/samescale-deploy rollback < /dev/null
curl --fail http://127.0.0.1:18580/api/health
```

该命令只替换 api/migrate 的镜像配置并启动 API，**不运行反向迁移**。失败时尝试恢复回滚前的
API；如果恢复也失败，命令报错并保留中断收据，需管理员处理。不要使用 `compose down`、
`down --volumes` 或全项目 restart 来回滚。

## 本轮演练与限制

实际演练结果在本轮 QA 记录与交付目录中说明。管理员可在已批准的 QA 环境重做健康失败演练：

```bash
sudo /usr/local/sbin/samescale-deploy --rehearse-health-failure FULL_MAIN_SHA < /dev/null
```

此选项不能经 deploy 密钥请求。它仍构建精确 main，附加演练标签使候选 image ID 与上一镜像
不同；经网关请求一个不存在的检查路径，产生真实 HTTP 失败，然后走相同的自动回滚流程。
这验证部署失败处理，不表示业务健康接口真的失效，也不产生新 Agent/产品验收结果。
预期退出非零，但实际 `/api/health` 和上一镜像应恢复正常；生产 workflow 不传演练选项。

- 镜像回滚不回滚已执行的数据库变更。未来迁移必须与上一 API 向后兼容（先扩展、后收缩）；
  非事务迁移失败可能已有部分变更，不能仅靠保留旧容器保证业务兼容。
- 健康检查验证 HTTP 与数据库连接，不覆盖全部业务 UAT。未验证破坏性 schema 变更、主机断电/
  SIGKILL、磁盘耗尽或 Docker daemon 故障；回滚也可能失败，必须保留人工修复途径。
- 会短暂中断 API。相同 API 地址未能回收时会失败/回滚；不自动修改 nginx 或网络配置。
- 不删除旧镜像、数据卷或私有构建记录，需要管理员按留存策略检查磁盘容量。
- 真正 GitHub-hosted runner 到服务器的自动路径，需要 environment/Secrets 配置且 PR 合并后
  才能验证。服务器演练和 PR CI 不等于该路径已经执行成功。
- 未来增加/重命名必要的 main CI workflow/job，应同步更新固定 gate 清单；不可把新检查遗漏。
