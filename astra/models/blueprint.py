from dataclasses import dataclass, field


@dataclass
class ArchitectureOverview:
    style: str = "modular-layered"
    boundaries: list = field(default_factory=list)
    core_modules: list = field(default_factory=list)
    external_integrations: list = field(default_factory=list)
    decisions: list = field(default_factory=list)


@dataclass
class ModuleBlueprint:
    name: str = ""
    purpose: str = ""
    responsibilities: list = field(default_factory=list)
    internal_files: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    api_contracts: list = field(default_factory=list)


@dataclass
class FileBlueprint:
    path: str = ""
    purpose: str = ""
    role: str = ""
    contains: list = field(default_factory=list)
    connects_to: list = field(default_factory=list)
    action: str = "preserve"
    reason: str = ""


@dataclass
class TechnologyStack:
    backend: str = "python"
    frontend: str = ""
    database: str = ""
    graph_storage: str = ""
    cache_layer: str = ""
    queue_system: str = ""
    ai_integration: str = ""
    decisions: list = field(default_factory=list)


@dataclass
class BuildStep:
    order: int = 0
    name: str = ""
    modules: list = field(default_factory=list)
    validation: list = field(default_factory=list)
    rollback: list = field(default_factory=list)


@dataclass
class MvpSpec:
    must_work: list = field(default_factory=list)
    excluded: list = field(default_factory=list)
    acceptance_checks: list = field(default_factory=list)


@dataclass
class RiskReport:
    technical: list = field(default_factory=list)
    scaling: list = field(default_factory=list)
    complexity: list = field(default_factory=list)
    dependency: list = field(default_factory=list)
    ai_context: list = field(default_factory=list)


@dataclass
class DependencyMap:
    module_dependencies: dict = field(default_factory=dict)
    critical_paths: list = field(default_factory=list)
    bottlenecks: list = field(default_factory=list)
    circular_risks: list = field(default_factory=list)


@dataclass
class ImplementationBlueprint:
    task: str = ""
    architecture: ArchitectureOverview = field(default_factory=ArchitectureOverview)
    modules: list = field(default_factory=list)
    files: list = field(default_factory=list)
    technology_stack: TechnologyStack = field(default_factory=TechnologyStack)
    build_order: list = field(default_factory=list)
    mvp: MvpSpec = field(default_factory=MvpSpec)
    risks: RiskReport = field(default_factory=RiskReport)
    dependency_map: DependencyMap = field(default_factory=DependencyMap)
    execution_roadmap: list = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
