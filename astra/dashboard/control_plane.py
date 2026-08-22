import time

from astra.models.dashboard import DashboardEvent, DashboardEventType, DashboardSystem


class DashboardControlPlane:
    def build(self, repository_index=None, knowledge_graph=None, context_pack=None, execution_state=None):
        events = []
        telemetry = {}
        graph_view = {}
        context_view = {}
        execution_view = execution_state or {}

        if repository_index:
            events.append(self._event(DashboardEventType.SCAN_PROGRESS, {
                "files_indexed": repository_index.metadata.files_indexed,
                "failures": repository_index.metadata.failures_count,
            }))
            telemetry["repository"] = {
                "files": repository_index.metadata.files_indexed,
                "languages": repository_index.language_summary.by_language,
            }

        if knowledge_graph:
            events.append(self._event(DashboardEventType.GRAPH_UPDATED, {
                "nodes": len(knowledge_graph.nodes),
                "edges": len(knowledge_graph.edges),
            }))
            graph_view = {
                "nodes": len(knowledge_graph.nodes),
                "edges": len(knowledge_graph.edges),
                "layers": {k: len(v) for k, v in knowledge_graph.architecture.layers.items()},
                "entry_points": knowledge_graph.entry_points,
            }

        if context_pack:
            events.append(self._event(DashboardEventType.CONTEXT_BUILT, {
                "nodes": len(context_pack.relevant_nodes),
                "files": len(context_pack.required_files),
            }))
            context_view = {
                "task": context_pack.task,
                "nodes": context_pack.relevant_nodes,
                "required_files": context_pack.required_files,
                "confidence": context_pack.confidence,
            }

        return DashboardSystem(
            graph_view=graph_view,
            context_view=context_view,
            execution_view=execution_view,
            telemetry=telemetry,
            events=events,
        )

    def _event(self, event_type, payload):
        return DashboardEvent(event_type=event_type, payload=payload, timestamp=time.time())
