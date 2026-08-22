from astra.core.logger import get_logger
from astra.models.symbol import Symbol, SymbolKind
from astra.models.dependency import Dependency, DependencyType

logger = get_logger("astra.parser.symbol_extractor")


KIND_MAP = {
    "function_definition": SymbolKind.FUNCTION,
    "class_definition": SymbolKind.CLASS,
    "method_definition": SymbolKind.METHOD,
    "assignment": SymbolKind.VARIABLE,
    "import_statement": SymbolKind.IMPORT,
    "import_from_statement": SymbolKind.IMPORT,
    "call": SymbolKind.CALL,
    "module": SymbolKind.MODULE,
    "interface_declaration": SymbolKind.INTERFACE,
    "struct_definition": SymbolKind.STRUCT,
    "enum_definition": SymbolKind.ENUM,
    "constant_definition": SymbolKind.CONSTANT,
    "type_definition": SymbolKind.TYPE,
    "property_definition": SymbolKind.PROPERTY,
    "parameter": SymbolKind.PARAMETER,
}

SKIP_TYPES = {
    "source_file", "program", "module", "translation_unit",
    "comment", "string", "integer", "float", "true", "false",
    "identifier", "type_identifier", "field_identifier",
    "assignment_expression", "binary_expression", "unary_expression",
    "return_statement", "if_statement", "for_statement",
    "while_statement", "block", "expression_statement",
    "arguments", "argument_list", "parameter_list",
    "parenthesized_expression", "attribute", "subscript",
}


class SymbolExtractor:
    def __init__(self):
        self._symbols = []
        self._dependencies = []

    def extract(self, ast_node, file_path="", source_lines=None):
        self._symbols = []
        self._dependencies = []
        if ast_node is None:
            return [], []
        self._walk(ast_node, file_path, source_lines, None)
        return self._symbols, self._dependencies

    def _walk(self, node, file_path, source_lines, parent_name):
        if node.node_type not in SKIP_TYPES:
            kind = KIND_MAP.get(node.node_type, SymbolKind.UNKNOWN)
            name = self._resolve_name(node)
            if name:
                symbol = Symbol(
                    name=name,
                    kind=kind,
                    file_path=file_path,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    col_start=node.col_start,
                    col_end=node.col_end,
                    parent=parent_name,
                    signature=self._build_signature(node),
                    body=self._extract_body(node, source_lines),
                )
                self._symbols.append(symbol)
                if kind == SymbolKind.IMPORT:
                    self._extract_import_deps(node, file_path)
                if kind == SymbolKind.CALL:
                    self._extract_call_deps(node, file_path, parent_name)
                if kind in (SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.METHOD):
                    parent_name = name
        for child in node.children:
            self._walk(child, file_path, source_lines, parent_name)

    def _resolve_name(self, node):
        for child in node.children:
            if child.node_type in ("identifier", "type_identifier", "field_identifier", "name"):
                return child.text.strip()
            if child.node_type == "attribute" and child.children:
                parts = []
                for c in child.children:
                    if c.text:
                        parts.append(c.text.strip())
                return ".".join(parts)
        return node.text.strip() if node.text else ""

    def _build_signature(self, node):
        parts = []
        for child in node.children:
            if child.node_type in ("identifier", "type_identifier", "name"):
                parts.append(child.text.strip())
            elif child.node_type in ("parameters", "parameter_list", "formal_parameters"):
                params = []
                for p in child.children:
                    if p.text and p.node_type not in ("(", ")", ",", "[", "]"):
                        params.append(p.text.strip().replace("\n", " ").replace("  ", " "))
                parts.append("(" + ", ".join(params) + ")")
        return " ".join(parts) if parts else ""

    def _extract_body(self, node, source_lines):
        if source_lines is None:
            return ""
        start = node.line_start - 1
        end = min(node.line_end, len(source_lines))
        if start < 0 or start >= len(source_lines):
            return ""
        lines = []
        for i in range(start, end):
            if isinstance(source_lines[i], tuple):
                lines.append(source_lines[i][1])
            else:
                lines.append(str(source_lines[i]))
        return "".join(lines)

    def _extract_import_deps(self, node, file_path):
        text = node.text.strip()
        for child in node.children:
            if child.node_type in ("dotted_name", "aliased_import", "import_prefix"):
                dep = Dependency(
                    source_file=file_path,
                    source_symbol="",
                    target_file="",
                    target_symbol=child.text.strip(),
                    dep_type=DependencyType.IMPORT,
                    line_number=node.line_start,
                )
                self._dependencies.append(dep)
                return
        if text:
            dep = Dependency(
                source_file=file_path,
                source_symbol="",
                target_file="",
                target_symbol=text,
                dep_type=DependencyType.IMPORT,
                line_number=node.line_start,
            )
            self._dependencies.append(dep)

    def _extract_call_deps(self, node, file_path, parent_name):
        for child in node.children:
            if child.node_type == "identifier" and child.text:
                dep = Dependency(
                    source_file=file_path,
                    source_symbol=parent_name or "",
                    target_file="",
                    target_symbol=child.text.strip(),
                    dep_type=DependencyType.CALL,
                    line_number=node.line_start,
                )
                self._dependencies.append(dep)
