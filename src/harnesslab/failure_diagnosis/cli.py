# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from harnesslab.failure_diagnosis.codex_backend import CodexSubscriptionBackend
from harnesslab.failure_diagnosis.service import diagnose
from harnesslab.failure_diagnosis.storage import load_input, read_bounded, replay, save_artifact

diagnosis_app = typer.Typer(
    no_args_is_help=True, help="对已验收失败的运行生成独立辅助诊断，不影响验收。"
)


@diagnosis_app.command("run")
def run(
    receipt: Annotated[Path, typer.Option(help="已有独立验收收据（只读）")],
    receipt_sha256: Annotated[str, typer.Option(help="验收收据文件SHA256")],
    public_packet: Annotated[Path, typer.Option(help="人工审阅过的公开证据摘录，禁止隐藏源码")],
    output: Annotated[Path, typer.Option(help="Git及原证据之外的新诊断目录")],
    confirm_subscription_diagnosis: Annotated[
        bool, typer.Option(help="单独授权本次外部Codex订阅诊断")
    ] = False,
    vendor: Annotated[Path | None, typer.Option(help="固定Codex CLI的vendor目录")] = None,
    credential_reference: Annotated[
        Path | None, typer.Option(help="既有ChatGPT登录文件的只读引用")
    ] = None,
    model: Annotated[str, typer.Option(help="订阅模型名")] = "gpt-6.1-sol",
    timeout_seconds: Annotated[
        float, typer.Option(min=1, max=600, help="模型及清理的超时秒数")
    ] = 120,
) -> None:
    try:
        item = load_input(receipt, receipt_sha256, public_packet)
        backend = None
        if confirm_subscription_diagnosis:
            if vendor is None or credential_reference is None:
                raise ValueError("explicit CLI and credential reference required")
            backend = CodexSubscriptionBackend(vendor, credential_reference, model=model)
        artifact = asyncio.run(diagnose(item, backend, timeout_seconds=timeout_seconds))
        digest = save_artifact(artifact, output, (receipt, public_packet))
    except Exception:
        typer.echo("无法读取已固定的失败验收或写入独立目录；请核对输入与权限。", err=True)
        raise typer.Exit(1) from None
    typer.echo(
        f"{artifact.mode}：{artifact.explanation.category.value}；{artifact.explanation.notice}"
    )
    typer.echo(f"降级原因：{artifact.fallback_reason.value}；产物SHA256：{digest}")


@diagnosis_app.command("replay")
def replay_command(
    export: Annotated[Path, typer.Option(help="独立诊断导出文件")],
    artifact_sha256: Annotated[str, typer.Option(help="可信的诊断产物SHA256")],
) -> None:
    try:
        artifact = replay(read_bounded(export), artifact_sha256)
    except Exception:
        typer.echo("诊断产物一致性校验失败。", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"离线一致性校验通过；{artifact.explanation.notice}。未调用模型。")
