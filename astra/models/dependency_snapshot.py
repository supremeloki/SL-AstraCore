from dataclasses import dataclass, field


@dataclass
class DependencySnapshot:
    direct: list = field(default_factory=list)
    upstream: list = field(default_factory=list)
    downstream: list = field(default_factory=list)
    cycles: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class RiskSummary:
    high_risk_nodes: list = field(default_factory=list)
    medium_risk_nodes: list = field(default_factory=list)
    volatile_nodes: list = field(default_factory=list)
    overall_risk_score: float = 0.0
    metadata: dict = field(default_factory=dict)
