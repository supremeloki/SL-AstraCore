from astra.core.logger import get_logger
from astra.models.task_analysis import TaskType
from astra.models.graph_node import NodeType

logger = get_logger("astra.context.strategy_engine")


class StrategyEngine:
    def get_strategy(self, task_type):
        strategies = {
            TaskType.BUG_FIX: self._bug_fix_strategy,
            TaskType.FEATURE_ADDITION: self._feature_strategy,
            TaskType.REFACTOR: self._refactor_strategy,
            TaskType.DEBUG_TRACE: self._debug_trace_strategy,
            TaskType.OPTIMIZATION: self._optimization_strategy,
            TaskType.ARCHITECTURE_REVIEW: self._architecture_strategy,
            TaskType.ANALYSIS: self._analysis_strategy,
        }
        return strategies.get(task_type, self._analysis_strategy)

    def _bug_fix_strategy(self):
        return {
            "depth_upstream": 2,
            "depth_downstream": 1,
            "include_config": True,
            "include_vault_rules": True,
            "node_priority": [
                NodeType.FUNCTION, NodeType.FILE, NodeType.CONFIG, NodeType.CLASS,
            ],
            "include_conflicts": True,
            "include_recent_changes": True,
            "max_nodes": 25,
        }

    def _feature_strategy(self):
        return {
            "depth_upstream": 1,
            "depth_downstream": 2,
            "include_config": True,
            "include_vault_rules": True,
            "node_priority": [
                NodeType.FILE, NodeType.CLASS, NodeType.PATTERN, NodeType.VAULT_CONCEPT,
            ],
            "include_conflicts": True,
            "include_recent_changes": False,
            "max_nodes": 30,
        }

    def _refactor_strategy(self):
        return {
            "depth_upstream": 3,
            "depth_downstream": 3,
            "include_config": False,
            "include_vault_rules": True,
            "node_priority": [
                NodeType.FILE, NodeType.MODULE, NodeType.CLASS, NodeType.PATTERN,
            ],
            "include_conflicts": True,
            "include_recent_changes": False,
            "max_nodes": 40,
        }

    def _debug_trace_strategy(self):
        return {
            "depth_upstream": 4,
            "depth_downstream": 2,
            "include_config": True,
            "include_vault_rules": False,
            "node_priority": [
                NodeType.FUNCTION, NodeType.FILE, NodeType.CLASS, NodeType.CONFIG,
            ],
            "include_conflicts": True,
            "include_recent_changes": True,
            "max_nodes": 35,
        }

    def _optimization_strategy(self):
        return {
            "depth_upstream": 1,
            "depth_downstream": 1,
            "include_config": False,
            "include_vault_rules": False,
            "node_priority": [
                NodeType.FUNCTION, NodeType.FILE, NodeType.PATTERN,
            ],
            "include_conflicts": False,
            "include_recent_changes": False,
            "max_nodes": 20,
        }

    def _architecture_strategy(self):
        return {
            "depth_upstream": 2,
            "depth_downstream": 2,
            "include_config": True,
            "include_vault_rules": True,
            "node_priority": [
                NodeType.MODULE, NodeType.PATTERN, NodeType.DECISION, NodeType.FILE,
            ],
            "include_conflicts": True,
            "include_recent_changes": False,
            "max_nodes": 50,
        }

    def _analysis_strategy(self):
        return {
            "depth_upstream": 2,
            "depth_downstream": 2,
            "include_config": True,
            "include_vault_rules": True,
            "node_priority": [
                NodeType.FILE, NodeType.MODULE, NodeType.VAULT_CONCEPT, NodeType.PATTERN,
            ],
            "include_conflicts": True,
            "include_recent_changes": False,
            "max_nodes": 35,
        }
