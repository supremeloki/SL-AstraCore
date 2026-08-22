from astra.core.logger import get_logger
from astra.models.ast_node import ASTNode

logger = get_logger("astra.parser.ast_builder")


class ASTBuilder:
    def __init__(self, ts_engine):
        self._engine = ts_engine

    def build(self, source_code, language, file_path=""):
        tree = self._engine.parse(source_code, language)
        if tree is None:
            return None
        root = tree.root_node
        return self._walk(root, file_path)

    def _walk(self, node, file_path, parent=None):
        ast_node = ASTNode(
            file_path=file_path,
            node_type=node.type,
            node_kind=node.type,
            text=node.text.decode("utf-8", errors="replace") if node.text else "",
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            col_start=node.start_point[1],
            col_end=node.end_point[1],
            parent_node=parent,
        )
        for child in node.children:
            child_ast = self._walk(child, file_path, ast_node)
            ast_node.children.append(child_ast)
        return ast_node
