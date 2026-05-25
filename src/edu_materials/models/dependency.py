from __future__ import annotations

from pydantic import Field

from . import SerializableModel


class DependencySpec(SerializableModel):
    id: str
    display_name: str
    kind: str
    module_name: str | None = None
    binary_names: list[str] = Field(default_factory=list)
    pip_name: str | None = None
    package_manager_ids: dict[str, str] = Field(default_factory=dict)
    package_manager_packages: dict[str, str] = Field(default_factory=dict)
    manual_instructions: dict[str, str] = Field(default_factory=dict)


class InstallOption(SerializableModel):
    method: str
    label: str
    command: list[str] = Field(default_factory=list)
    notes: str | None = None
    auto_supported: bool = False


class DependencyIssue(SerializableModel):
    id: str
    display_name: str
    kind: str
    required_for: list[str] = Field(default_factory=list)
    is_required: bool = False
    detected: bool = False
    detected_location: str | None = None
    can_auto_install: bool = False
    message: str
    install_options: list[InstallOption] = Field(default_factory=list)


class CapabilityReport(SerializableModel):
    target: str
    ready: bool
    missing_required_count: int = 0
    issues: list[DependencyIssue] = Field(default_factory=list)
    satisfied_capabilities: list[str] = Field(default_factory=list)
    unavailable_capabilities: list[str] = Field(default_factory=list)


class InstallationAttempt(SerializableModel):
    dependency_id: str
    status: str
    command: list[str] = Field(default_factory=list)
    message: str


class InstallationSummary(SerializableModel):
    mode: str
    requested_count: int = 0
    executed_count: int = 0
    attempts: list[InstallationAttempt] = Field(default_factory=list)
