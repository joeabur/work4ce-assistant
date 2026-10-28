"""Versioned CDK contracts. Only trusted backend code supplies execution context."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Work4ceError(Exception):
    """Public code only; external exception details must not escape the gateway."""

    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


def validate_schema(schema: dict[str, Any]) -> None:
    # Local, bounded JSON schemas only: references must not trigger network I/O.
    raw = canonical(schema)
    if len(raw) > 32_000:
        raise ValueError("schema too large")

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 24:
            raise ValueError("schema too deep")
        if isinstance(value, dict):
            if any(k in value for k in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise ValueError("schema references are not supported")
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)

    visit(schema)
    Draft202012Validator.check_schema(schema)
    if schema.get("type") != "object":
        raise ValueError("top-level schema must be an object")


class CapabilityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=160)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+$", max_length=16)
    description: str = Field(min_length=1, max_length=1000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    execution_class: Literal["read", "write"] = "read"
    required_permissions: tuple[str, ...] = ("events:read",)
    resource_scope: str = "synthetic-events"
    side_effects: bool = False
    data_classification: Literal["synthetic", "internal", "restricted"] = "synthetic"
    approval_required: bool = False
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_result_bytes: int = Field(default=128_000, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def schemas_are_local(self) -> CapabilityManifest:
        validate_schema(self.input_schema)
        validate_schema(self.output_schema)
        return self

    def validate_arguments(self, data: dict[str, Any]) -> None:
        if len(canonical(data)) > 16_000:
            raise Work4ceError("arguments_too_large", 422)
        validator = Draft202012Validator(self.input_schema, format_checker=FormatChecker())
        if not validator.is_valid(data):
            raise Work4ceError("invalid_arguments", 422)

    def validate_result(self, data: dict[str, Any]) -> None:
        if len(canonical(data).encode()) > self.max_result_bytes:
            raise Work4ceError("result_too_large", 502)
        validator = Draft202012Validator(self.output_schema, format_checker=FormatChecker())
        if not validator.is_valid(data):
            raise Work4ceError("invalid_connector_result", 502)


class ConnectorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    api_version: Literal["work4ce.io/v1alpha1"] = "work4ce.io/v1alpha1"
    connector_id: str = Field(pattern=r"^[a-z][a-z0-9-]+$", max_length=80)
    name: str = Field(min_length=1, max_length=120)
    publisher: str = "work4ce-reference"
    version: str = "0.1.0"
    protocol: str = Field(min_length=1, max_length=40)
    tenant_id: str
    synthetic: bool
    capability: CapabilityManifest
    credential_reference: str | None = None
    default_enabled: Literal[False] = False


@dataclass(frozen=True)
class ExecutionContext:
    tenant_id: str
    subject: str
    permissions: frozenset[str]
    allowed_connectors: frozenset[str]
    synthetic: bool


class Connector(Protocol):
    async def health(self) -> bool: ...
    async def discover(self) -> list[dict[str, Any]]: ...
    async def invoke(self, capability_id: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
