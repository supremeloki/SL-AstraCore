from dataclasses import dataclass, field
from enum import Enum


class ArchitectureLayer(Enum):
    PRESENTATION = "presentation"
    APPLICATION = "application"
    DOMAIN = "domain"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class ModuleType(Enum):
    CORE = "core"
    SERVICE = "service"
    ADAPTER = "adapter"
    UTILITY = "utility"
    CONFIG = "config"
    DATA = "data"
    VAULT_LINKED = "vault-linked"


class Stability(Enum):
    STABLE = "stable"
    SEMI_STABLE = "semi-stable"
    VOLATILE = "volatile"


@dataclass
class FileSemantic:
    path: str = ""
    purpose: str = ""
    role: str = ""
    type: ModuleType = ModuleType.UTILITY
    responsibilities: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    dependents: list = field(default_factory=list)
    internal_entities: list = field(default_factory=list)
    architecture_layer: ArchitectureLayer = ArchitectureLayer.UNKNOWN
    stability: Stability = Stability.SEMI_STABLE
    complexity_score: float = 0.0
    risk_level: str = "low"
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
