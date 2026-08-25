from dataclasses import dataclass

from astra.core.logger import get_logger
from astra.graph.conflict_enricher import detect_circular_dependencies, detect_naming_conflicts
from astra.graph.pattern_enricher import detect_design_patterns, detect_naming_conventions
from astra.graph.vault_enricher import build_vault_code_edges
from astra.ir.models import IRDependency, IRFileNode, IRVaultConceptNode
from astra.ir.models import NodeType as IRNodeType
from astra.models.conflict import ConflictSeverity, ConflictType
from astra.models.graph_edge import EdgeType, GraphEdge
from astra.models.graph_node import GraphNode, NodeType
from astra.models.knowledge_graph import ArchitectureGraph, KnowledgeGraph, PatternGraphNode
from astra.models.parser import StructuralKind

logger = get_logger("astra.graph.graph_engine")

_SEVERITY_MAP = {
    "low": ConflictSeverity.LOW,
    "medium": ConflictSeverity.MEDIUM,
    "high": ConflictSeverity.HIGH,
}
_CATEGORY_MAP = {
    "naming": ConflictType.NAMING,
    "circular_dependency": ConflictType.ARCHITECTURE,
}


@dataclass
class GraphConflict:
    """Conflict record shaped for all graph consumers.

    graph_query reads .id, runtime_brain/execution_engine read enum .value,
    hence neither the raw ConflictMatch nor models.Conflict fits alone.
    """

    id: str
    source_a: str
    source_b: str
    conflict_type: ConflictType
    severity: ConflictSeverity
    description: str
    confidence: float


class DomainGraphEngine:
    def build(self, repository_index, parse_index):
        nodes = []
        edges = []
        node_index = {}

        for file_meta in repository_index.files:
            node = GraphNode(
                id=f"file:{file_meta.rel_path}",
                label=file_meta.rel_path,
                node_type=NodeType.FILE,
                properties={
                    "file_id": file_meta.id,
                    "category": file_meta.category.value,
                    "language": file_meta.language,
                    "kind": file_meta.kind.value,
                    "size_bytes": file_meta.size_bytes,
                    "hash": file_meta.hash_value,
                    "risk": "medium" if file_meta.category.value in ("source", "config") else "low",
                },
                layer=self._layer_for(file_meta),
                confidence=0.9,
            )
            self._add_node(node, nodes, node_index)

        for parsed_file in parse_index.files:
            file_node_id = f"file:{parsed_file.file_path}"
            for element in parsed_file.elements:
                node = GraphNode(
                    id=f"symbol:{element.id}",
                    label=element.name,
                    node_type=self._node_type(element.kind),
                    properties={
                        "file": element.file_path,
                        "kind": element.kind.value,
                        "line_start": element.line_start,
                        "line_end": element.line_end,
                        "signature": element.signature,
                        "metadata": element.metadata,
                    },
                    layer="code",
                    confidence=parsed_file.confidence,
                )
                self._add_node(node, nodes, node_index)
                edges.append(GraphEdge(
                    from_node=node.id,
                    to_node=file_node_id,
                    edge_type=EdgeType.BELONGS_TO,
                    weight=1.0,
                    confidence=parsed_file.confidence,
                ))

            for dep in parsed_file.dependencies:
                target = self._resolve_dependency_target(dep.target, node_index)
                edges.append(GraphEdge(
                    from_node=file_node_id,
                    to_node=target,
                    edge_type=self._edge_type(dep.signal_type),
                    weight=1.0,
                    confidence=dep.confidence,
                    properties={"target": dep.target, "line": dep.line_number},
                ))

        architecture = self._architecture(nodes)
        graph = KnowledgeGraph(
            nodes=nodes,
            edges=edges,
            node_index=node_index,
            architecture=architecture,
            entry_points=architecture.entry_points,
            metadata={
                "source": "DomainGraphEngine",
                "repository_files": len(repository_index.files),
                "parsed_files": len(parse_index.files),
                "parser_failures": len(parse_index.failures),
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            },
        )

        ir_files, ir_deps, vault_concepts = self._ir_inputs(repository_index, parse_index, node_index)
        self._enrich(graph, nodes, ir_files, ir_deps, vault_concepts)

        logger.info("Domain graph built: nodes=%d edges=%d", len(nodes), len(edges))
        return graph

    def _ir_inputs(self, repository_index, parse_index, node_index):
        ir_files = [
            IRFileNode(
                id=f"file:{f.rel_path}",
                type=IRNodeType.FILE,
                name=f.rel_path.split("/")[-1],
                source="scanner",
                file_path=f.rel_path,
                language=f.language or "",
            )
            for f in repository_index.files
        ]
        ir_deps = [
            IRDependency(
                source_file=d.source_file,
                target_module=d.target,
                line=d.line_number,
            )
            for d in parse_index.dependencies
        ]
        vault_concepts = []
        for parsed in parse_index.files:
            linked = tuple(
                f"file:{dep.target}"
                for dep in parsed.dependencies
                if dep.signal_type == "links_to"
                and f"file:{dep.target}" in node_index
            )
            for element in parsed.elements:
                if element.kind == StructuralKind.HEADING:
                    vault_concepts.append(IRVaultConceptNode(
                        id=f"vault:{parsed.file_path}:{element.name}",
                        type=IRNodeType.VAULT_CONCEPT,
                        name=element.name,
                        source="md-parser",
                        file_path=parsed.file_path,
                        linked_code_paths=linked,
                    ))
        return ir_files, ir_deps, vault_concepts

    def _enrich(self, graph, nodes, ir_files, ir_deps, vault_concepts):
        graph.conflicts.conflicts = self._conflicts(ir_files, ir_deps)
        graph.patterns.patterns = self._patterns(ir_files)
        code_nodes = [n for n in nodes if n.node_type == NodeType.FILE]

        for e in build_vault_code_edges(vault_concepts, code_nodes):
            graph.edges.append(GraphEdge(
                from_node=e.from_node,
                to_node=e.to_node,
                edge_type=EdgeType.REFERENCES,
                weight=e.weight,
                confidence=e.confidence,
            ))

    def _conflicts(self, ir_files, ir_deps):
        matches = list(detect_naming_conflicts(ir_files))
        matches.extend(detect_circular_dependencies(ir_deps))
        conflicts = []
        for m in matches:
            conflicts.append(GraphConflict(
                id=f"conflict:{m.category}:{m.source_a}:{m.source_b}",
                source_a=m.source_a,
                source_b=m.source_b,
                conflict_type=_CATEGORY_MAP.get(m.category, ConflictType.LOGIC),
                severity=_SEVERITY_MAP.get(m.severity, ConflictSeverity.MEDIUM),
                description=m.description,
                confidence=m.confidence,
            ))
        return conflicts

    def _patterns(self, ir_files):
        matches = list(detect_design_patterns(ir_files))
        matches.extend(detect_naming_conventions(ir_files))
        patterns = []
        for p in matches:
            patterns.append(PatternGraphNode(
                id=f"pattern:{p.name}",
                name=p.name,
                pattern_type=p.name,
                occurrences=len(p.locations),
                locations=list(p.locations),
                affects=[f"file:{loc}" for loc in p.locations],
                confidence=p.confidence,
            ))
        return patterns

    def _add_node(self, node, nodes, node_index):
        if node.id in node_index:
            return
        nodes.append(node)
        node_index[node.id] = node

    def _node_type(self, kind):
        if kind == StructuralKind.CLASS:
            return NodeType.CLASS
        if kind in (StructuralKind.FUNCTION, StructuralKind.METHOD):
            return NodeType.FUNCTION
        if kind == StructuralKind.MODULE:
            return NodeType.MODULE
        return NodeType.SYMBOL

    def _edge_type(self, signal_type):
        if signal_type == "import":
            return EdgeType.DEPENDS_ON
        if signal_type == "call":
            return EdgeType.USES
        if signal_type == "links_to":
            return EdgeType.REFERENCES
        return EdgeType.REFERENCES

    def _resolve_dependency_target(self, target, node_index):
        file_id = f"file:{target}"
        if file_id in node_index:
            return file_id
        return f"external:{target}"

    def _layer_for(self, file_meta):
        path = file_meta.rel_path.replace("\\", "/")
        if path.startswith("astra/parser"):
            return "parser"
        if path.startswith("astra/scanner"):
            return "scanner"
        if path.startswith("astra/graph") or path.startswith("astra/knowledge"):
            return "graph"
        if path.startswith("astra/context"):
            return "context"
        if path.startswith("astra/runtime"):
            return "runtime"
        if path.startswith("astra/dashboard"):
            return "dashboard"
        if path.startswith("astra/plugins"):
            return "plugins"
        return "core" if path.startswith("astra/core") else "unknown"

    def _architecture(self, nodes):
        layers = {}
        modules = {}
        entry_points = []
        for node in nodes:
            layers.setdefault(node.layer or "unknown", []).append(node.id)
            if node.node_type == NodeType.FILE:
                module = "/".join(node.label.replace("\\", "/").split("/")[:2])
                modules.setdefault(module, []).append(node.id)
                if any(part in node.label.lower() for part in ("main", "cli", "app", "__init__")):
                    entry_points.append(node.id)
        return ArchitectureGraph(
            layers=layers,
            modules=[{"name": name, "nodes": ids} for name, ids in sorted(modules.items())],
            entry_points=entry_points,
        )
