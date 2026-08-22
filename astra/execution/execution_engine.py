import ast
import os

from astra.core.logger import get_logger
from astra.models.execution import (
    ChangeSpec,
    ChangeType,
    DependencyImpactReport,
    ExecutionResult,
    FileChangeMap,
    Patch,
    RollbackPlan,
)

logger = get_logger("astra.execution.execution_engine")


class ExecutionEngine:
    def __init__(self, root_path=None):
        self._root = root_path or os.getcwd()

    def build_patch_set(self, change_specs, implementation_blueprint=None, context_pack=None, knowledge_graph=None):
        logger.info("Execution started: patch planning")
        patches = []
        for spec in self._ordered_specs(change_specs, knowledge_graph):
            patch = self._to_patch(spec)
            patch.validation_errors.extend(self._validate_patch(patch))
            patches.append(patch)

        result = ExecutionResult(
            patch_set=patches,
            file_change_map=self._file_change_map(patches),
            dependency_impact=self._dependency_impact(patches, context_pack, knowledge_graph),
            risk_analysis=self._risk_analysis(patches, context_pack),
            rollback_plan=self._rollback_plan(patches),
            execution_log=self._execution_log(patches, implementation_blueprint),
            applied=False,
            confidence=self._confidence(patches),
        )
        logger.info("Execution complete: patches=%d confidence=%.2f", len(patches), result.confidence)
        return result

    def from_blueprint(self, implementation_blueprint, context_pack=None, knowledge_graph=None):
        specs = []
        for file_plan in implementation_blueprint.files:
            if file_plan.action not in ("create", "modify", "delete"):
                continue
            change_type = {
                "create": ChangeType.CREATE_FILE,
                "modify": ChangeType.MODIFY_FILE,
                "delete": ChangeType.DELETE_FILE,
            }[file_plan.action]
            specs.append(ChangeSpec(
                file_path=file_plan.path,
                change_type=change_type,
                after="",
                reason=file_plan.reason or "blueprint selected file",
                dependencies_affected=file_plan.connects_to,
                risk_level="medium" if file_plan.action == "modify" else "low",
                confidence=implementation_blueprint.confidence,
            ))
        return self.build_patch_set(specs, implementation_blueprint, context_pack, knowledge_graph)

    def apply(self, execution_result):
        errors = [err for patch in execution_result.patch_set for err in patch.validation_errors]
        if errors:
            execution_result.execution_log.append({"status": "blocked", "errors": errors})
            return execution_result

        for patch in execution_result.patch_set:
            path = self._resolve(patch.file_path)
            if patch.change_type == ChangeType.DELETE_FILE:
                if os.path.exists(path):
                    os.remove(path)
                continue
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(patch.after)
        execution_result.applied = True
        execution_result.execution_log.append({"status": "applied", "patches": len(execution_result.patch_set)})
        return execution_result

    def _ordered_specs(self, change_specs, knowledge_graph):
        if not knowledge_graph:
            return list(change_specs)
        depth = {}
        for edge in knowledge_graph.edges:
            depth[edge.to_node] = depth.get(edge.to_node, 0) + 1

        def score(spec):
            node_id = f"file:{spec.file_path}"
            return depth.get(node_id, 0)

        return sorted(change_specs, key=score)

    def _to_patch(self, spec):
        before = spec.before
        path = self._resolve(spec.file_path)
        if before is None and os.path.exists(path) and spec.change_type != ChangeType.CREATE_FILE:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                before = f.read()
        return Patch(
            file_path=spec.file_path,
            change_type=spec.change_type,
            before=before,
            after=spec.after,
            reason=spec.reason,
            dependencies_affected=spec.dependencies_affected,
            risk_level=spec.risk_level,
            confidence=spec.confidence,
        )

    def _validate_patch(self, patch):
        errors = []
        path = self._resolve(patch.file_path)
        if patch.change_type == ChangeType.CREATE_FILE and os.path.exists(path):
            errors.append("create_file target already exists")
        if patch.change_type in (ChangeType.MODIFY_FILE, ChangeType.DELETE_FILE) and not os.path.exists(path):
            errors.append("target file does not exist")
        if patch.change_type != ChangeType.DELETE_FILE and patch.file_path.endswith(".py") and patch.after:
            try:
                ast.parse(patch.after)
            except SyntaxError as exc:
                errors.append(f"python syntax error: {exc}")
        if patch.change_type != ChangeType.DELETE_FILE and not patch.after:
            errors.append("after state is required for executable file changes")
        return errors

    def _file_change_map(self, patches):
        change_map = FileChangeMap()
        for patch in patches:
            if patch.change_type == ChangeType.CREATE_FILE:
                change_map.created.append(patch.file_path)
            elif patch.change_type == ChangeType.MODIFY_FILE:
                change_map.modified.append(patch.file_path)
            elif patch.change_type == ChangeType.DELETE_FILE:
                change_map.deleted.append(patch.file_path)
            elif patch.change_type == ChangeType.REFACTOR_MODULE:
                change_map.refactored.append(patch.file_path)
            elif patch.change_type == ChangeType.INTEGRATE_SYSTEM:
                change_map.integrated.append(patch.file_path)
        return change_map

    def _dependency_impact(self, patches, context_pack, knowledge_graph):
        direct = []
        if context_pack:
            direct.extend(context_pack.critical_dependencies)
        breaking = [
            patch.file_path for patch in patches
            if patch.change_type == ChangeType.DELETE_FILE or patch.risk_level == "high"
        ]
        circular = []
        if knowledge_graph and knowledge_graph.conflicts:
            circular = [
                c.description for c in knowledge_graph.conflicts.conflicts
                if getattr(c, "conflict_type", None) and c.conflict_type.value == "architecture"
            ]
        return DependencyImpactReport(
            direct=direct,
            upstream=[],
            downstream=[],
            breaking_changes=breaking,
            circular_risks=circular,
        )

    def _risk_analysis(self, patches, context_pack):
        risks = []
        for patch in patches:
            if patch.validation_errors:
                risks.append({"file": patch.file_path, "risk": "validation_failed", "details": patch.validation_errors})
            elif patch.risk_level in ("high", "medium"):
                risks.append({"file": patch.file_path, "risk": patch.risk_level, "details": patch.reason})
        if context_pack:
            risks.extend({"context_risk": risk} for risk in context_pack.hidden_risks)
        return risks

    def _rollback_plan(self, patches):
        steps = []
        for patch in reversed(patches):
            if patch.change_type == ChangeType.CREATE_FILE:
                steps.append({"file": patch.file_path, "action": "delete created file"})
            elif patch.change_type == ChangeType.DELETE_FILE:
                steps.append({"file": patch.file_path, "action": "restore deleted file", "content": patch.before or ""})
            else:
                steps.append({"file": patch.file_path, "action": "restore previous content", "content": patch.before or ""})
        return RollbackPlan(steps=steps, recovery_notes=["Apply rollback steps in listed order."])

    def _execution_log(self, patches, implementation_blueprint):
        log = [{"event": "patch_set_built", "patches": len(patches)}]
        if implementation_blueprint:
            log.append({"event": "blueprint_used", "task": implementation_blueprint.task})
        return log

    def _confidence(self, patches):
        if not patches:
            return 0.0
        valid = sum(1 for p in patches if not p.validation_errors)
        return round(valid / len(patches), 2)

    def _resolve(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(self._root, path)
