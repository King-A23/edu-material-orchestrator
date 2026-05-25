from __future__ import annotations

from typing import Callable

from ..models.dependency import DependencyIssue, InstallOption, InstallationAttempt, InstallationSummary
from .subprocesses import CommandExecutionError, run_command


ConfirmCallback = Callable[[DependencyIssue, InstallOption], bool]
EmitCallback = Callable[[str], None]


def choose_install_option(issue: DependencyIssue) -> InstallOption | None:
    for option in issue.install_options:
        if option.auto_supported and option.command:
            return option
    return None


def apply_installation_policy(
    issues: list[DependencyIssue],
    mode: str,
    confirm_callback: ConfirmCallback | None = None,
    emit_callback: EmitCallback | None = None,
) -> InstallationSummary:
    summary = InstallationSummary(mode=mode, requested_count=len(issues))
    emit = emit_callback or (lambda message: None)

    for issue in issues:
        option = choose_install_option(issue)
        if option is None:
            summary.attempts.append(
                InstallationAttempt(
                    dependency_id=issue.id,
                    status="skipped",
                    message="No automatic installation option is available.",
                )
            )
            continue

        if mode == "never":
            summary.attempts.append(
                InstallationAttempt(
                    dependency_id=issue.id,
                    status="skipped",
                    message="Installation policy is set to never.",
                )
            )
            continue

        if mode == "ask":
            if confirm_callback is None or not confirm_callback(issue, option):
                summary.attempts.append(
                    InstallationAttempt(
                        dependency_id=issue.id,
                        status="declined",
                        command=option.command,
                        message="Installation was declined by the user.",
                    )
                )
                continue

        emit(f"Installing {issue.display_name} using {option.method}.")
        try:
            run_command(option.command, timeout_seconds=1200)
        except CommandExecutionError as error:
            summary.attempts.append(
                InstallationAttempt(
                    dependency_id=issue.id,
                    status="failed",
                    command=option.command,
                    message=str(error),
                )
            )
            continue

        summary.executed_count += 1
        summary.attempts.append(
            InstallationAttempt(
                dependency_id=issue.id,
                status="installed",
                command=option.command,
                message=f"Installed {issue.display_name}.",
            )
        )

    return summary
