# PR #17：API IP 变化演练（2026-10-13 UTC）

在原部署分支上更新控制器，仅构建当前 main
`a0ab9e8d5170d99703781046e7b853063c8e6891`，没有部署 PR 的产品源码。
本机即已授权 GCP QA 主机。原脏 checkout、冻结证据和数据库内容未作修改；
单次 `alembic upgrade head` 的数据库已在 head，不代表测试过新的 schema 变更。

## 网关与权限

管理员用 `ops.gcp.gateway` 修改现有 bind-mounted nginx.conf，原地写入保留 inode，
`nginx -t` 后 graceful reload。gateway 容器 ID/启动时间未变化；其请求白名单、
403 拒绝策略与代理头部内容和原备份逐字一致。重复配置通过，未再 reload。
Docker DNS resolver 为 `127.0.0.11`，缓存 5 秒；变量代理不含 URI 后缀。

部署 workflow、CI gate、forced-command、sudoers 设计未改。服务器上 sudoers、
authorized_keys、SSH 入口、launcher、CI gate 的 SHA256 在前后核对一致。
受限 SSH 对当前 main 的重复请求返回 `ALREADY_HEALTHY`，无额外 API 重建。

## 实际地址变化与结果

管理员辅助脚本调用已安装的真实 `Host.prepare/begin/rollout`，在删除 API 容器后，
用两个带唯一演练名称/标签的临时容器占住刚释放的 IP；无卷、无对外端口、无 api 别名。
它只插入地址占用操作，构建、CI 复核、迁移、镜像切换、HTTP 检查和回滚均调用真实控制器。
所有地址占用容器在 finally 中删除；没有扩大 deploy 用户或 SSH 的权限。

| 场景 | 地址 | 实际结果 |
| --- | --- | --- |
| 成功部署 | `172.24.0.4 → 172.24.0.5` | 新镜像通过 gateway 的 HTTP/JSON/数据库健康检查并写入成功收据 |
| 候选失败 | `172.24.0.5 → 172.24.0.4` | 既有演练选项请求不存在的检查路径，真实 HTTP 403，控制器抛出部署失败 |
| 自动恢复 | `172.24.0.4 → 172.24.0.6` | 上一 image ID 恢复，正常健康检查通过；失败候选未写入成功收据 |

成功演练镜像/最后线上镜像：
`sha256:9d4e2b196416a35c871fce7d74c30c38d5233e59d5a3bbed2545ee639be3b3dc`。
失败候选：`sha256:f18c8a7e52916726a8a09312c2081369681ed400136f0164b0623b37f3707955`。
两者 SOURCE_REVISION 均为上述 main SHA。部署失败是注入的探测失败，不是业务故障声明。
重建期间观察到短暂 502 后恢复，未重启/reload gateway，不承诺零停机。

第一次演练辅助脚本在 API stop 后读取 IP，因 Docker 清空该地址导致中断。
随后真实 `Host.recover` 从 pending 收据恢复旧镜像并通过健康检查，再修正辅助脚本为
停机前记录地址。该初次失败保留在日志中，未计为通过。最终没有 pending 收据。

57 个保护范围内容器（包括 PostgreSQL、gateway、tunnel、其他项目）的 ID、镜像、
启动时间、运行状态在前后完全一致，旧镜像和数据卷未删除。正常 GET 首页/health、
编码路径与查询参数请求通过；POST health 与不存在的演练路径仍为 403。
HEAD health 为既有 404，直接请求 API 同为 404，未改产品路由行为。

## 离线验证与证据位置

- `python3 -m unittest tests.test_gcp_deploy tests.test_ci_routing`：32 个测试通过
  （部署 22 + CI 路由 10），包含不同 IP 的真实 Host 激活/回滚、恢复收据清理、错误镜像/
  网络/别名拒绝、bind inode 保留、配置验证/reload/健康失败恢复及白名单字节保留。
- Ruff/format 全仓通过（858 files），`mypy src tests scripts ops` 通过（439 sources）。
- 同一 PR 的最终 SHA 远端 Fast CI、Offline Regression 与 Deployment contracts
  在最终交付时另行核对；此记录不预报 CI 结果。

主机交付目录：`/home/dev/samescale-deliverables/gcp-ip-change-20261013/`。
`success.log` 保留初次辅助脚本失败；`success-retry.log`、`failure-rollback.log` 为通过的
演练；`rehearse.py` 为管理员专用地址占用辅助脚本；`server-closeout.json` 是无秘密的
最终状态与保护检查。原始构建/迁移输出仍只在 root-only 私有日志中。

## 未验证与边界

GitHub environment 仍未配置（只读核对为空），未启用自动部署、未合并 PR。
GitHub-hosted runner 到服务器的完整路径尚未验证。本轮没有测试破坏性迁移、真实失败 SQL、
主机断电、SIGKILL、磁盘耗尽或 Docker/DNS 服务故障，也未做完整业务 UAT。
迁移只向前；恢复镜像不恢复 schema，新迁移必须兼容上一版代码。
私钥尚待用户导入 Secret；文档要求导入成功后删除服务器暂存私钥，仅保留公钥。
