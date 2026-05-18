from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


PluginState = Literal[
    "not_installed",
    "installed_disabled",
    "enabled_not_configured",
    "enabled_starting",
    "enabled_unhealthy",
    "ready",
    "busy",
]


class PluginEntrypoint(BaseModel):
    base_url: str
    health: str


class PluginCapability(BaseModel):
    modes: list[str] = Field(default_factory=list)
    entrypoint: PluginEntrypoint


class PluginManifest(BaseModel):
    id: str
    name: str
    version: str
    protocol_version: str
    platforms: list[str] = Field(default_factory=list)
    capabilities: dict[str, PluginCapability] = Field(default_factory=dict)


class PluginStatusRead(BaseModel):
    plugin_id: str
    plugin_name: str
    plugin_version: str
    protocol_version: str
    enabled: bool = False
    state: PluginState
    health: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[dict[str, Any]] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)


class PluginConfigUpdateInput(BaseModel):
    enabled: bool = False
    provider_profile: str = "openai_compatible"
    base_url: HttpUrl | None = None
    api_key: str | None = None
    model: str | None = None


class PluginConfigRead(BaseModel):
    enabled: bool = False
    provider_profile: str = "openai_compatible"
    base_url: str | None = None
    api_key_configured: bool = False
    model: str | None = None
