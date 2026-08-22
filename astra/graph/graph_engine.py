from astra.core.logger import get_logger
from astra.models.graph_edge import EdgeType, GraphEdge
from astra.models.graph_node import GraphNode, NodeType
from astra.models.knowledge_graph import ArchitectureGraph, KnowledgeGraph
from astra.models.parser import StructuralKind

logger = get_logger("astra.graph.graph_engine")


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
        logger.info("Domain graph built: nodes=%d edges=%d", len(nodes), len(edges))
        return graph

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
