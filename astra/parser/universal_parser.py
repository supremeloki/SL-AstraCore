import ast
import re

from astra.core.logger import get_logger
from astra.models.file_node import FileCategory
from astra.models.parser import (
    DependencySignal,
    ParsedFile,
    ParseIndex,
    ParserFailure,
    StructuralElement,
    StructuralKind,
)

logger = get_logger("astra.parser.universal_parser")


class UniversalParser:
    def __init__(self, max_read_bytes=2_000_000):
        self._max_read_bytes = max_read_bytes

    def parse_repository(self, repository_index):
        parsed_files = []
        failures = []
        for file_meta in repository_index.files:
            try:
                parsed = self.parse_file(file_meta)
                if parsed:
                    parsed_files.append(parsed)
            except Exception as exc:
                failures.append(ParserFailure(
                    file_path=file_meta.rel_path,
                    parser_name=self._parser_name(file_meta),
                    error=str(exc),
                    recoverable=True,
                ))
        return ParseIndex(
            files=parsed_files,
            failures=failures,
            metadata={
                "source": "UniversalParser",
                "input_files": len(repository_index.files),
                "parsed_files": len(parsed_files),
                "failures": len(failures),
            },
        )

    def parse_file(self, file_meta):
        if file_meta.is_binary:
            return self._binary_result(file_meta)
        source = self._read_text(file_meta)
        parser_name = self._parser_name(file_meta)
        if file_meta.language == "python":
            return self._parse_python(file_meta, source, parser_name)
        if file_meta.language == "markdown" or file_meta.category == FileCategory.KNOWLEDGE:
            return self._parse_markdown(file_meta, source, parser_name)
        if file_meta.category == FileCategory.CONFIG:
            return self._parse_config(file_meta, source, parser_name)
        return self._parse_generic(file_meta, source, parser_name)

    def _parse_python(self, file_meta, source, parser_name):
        elements = []
        dependencies = []
        tree = ast.parse(source or "")
        module_id = self._element_id(file_meta, "module", file_meta.rel_path, 1)
        elements.append(StructuralElement(
            id=module_id,
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            name=file_meta.rel_path,
            kind=StructuralKind.MODULE,
            line_start=1,
            line_end=max(1, file_meta.lines_count),
        ))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                elements.append(self._element(file_meta, node.name, StructuralKind.FUNCTION, node.lineno, getattr(node, "end_lineno", node.lineno)))
            elif isinstance(node, ast.ClassDef):
                elements.append(self._element(file_meta, node.name, StructuralKind.CLASS, node.lineno, getattr(node, "end_lineno", node.lineno)))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                target = self._import_target(node)
                elements.append(self._element(file_meta, target, StructuralKind.IMPORT, node.lineno, node.lineno))
                dependencies.append(DependencySignal(
                    source_file=file_meta.rel_path,
                    target=target,
                    signal_type="import",
                    line_number=node.lineno,
                    confidence=0.9,
                ))
            elif isinstance(node, ast.Call):
                target = self._call_target(node)
                if target:
                    dependencies.append(DependencySignal(
                        source_file=file_meta.rel_path,
                        target=target,
                        signal_type="call",
                        line_number=getattr(node, "lineno", 0),
                        confidence=0.5,
                    ))
        return ParsedFile(
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            language=file_meta.language or "",
            parser_name=parser_name,
            elements=elements,
            dependencies=dependencies,
            confidence=0.85,
        )

    def _parse_markdown(self, file_meta, source, parser_name):
        elements = []
        dependencies = []
        heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
        wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
        for line_no, line in enumerate((source or "").splitlines(), 1):
            heading = heading_re.match(line)
            if heading:
                elements.append(self._element(
                    file_meta,
                    heading.group(2).strip(),
                    StructuralKind.HEADING,
                    line_no,
                    line_no,
                    metadata={"level": len(heading.group(1))},
                ))
            for match in wikilink_re.finditer(line):
                dependencies.append(DependencySignal(
                    source_file=file_meta.rel_path,
                    target=match.group(1).strip(),
                    signal_type="links_to",
                    line_number=line_no,
                    confidence=0.8,
                ))
        return ParsedFile(
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            language=file_meta.language or "markdown",
            parser_name=parser_name,
            elements=elements or [self._fallback_element(file_meta)],
            dependencies=dependencies,
            confidence=0.75,
        )

    def _parse_config(self, file_meta, source, parser_name):
        data = self._load_structured_config(file_meta.rel_path, source)
        if data is not None:
            return ParsedFile(
                file_id=file_meta.id,
                file_path=file_meta.rel_path,
                language=file_meta.language or "",
                parser_name=parser_name,
                elements=self._config_key_elements(file_meta, data),
                confidence=0.8,
            )
        elements = []
        for line_no, line in enumerate((source or "").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split(":", 1)[0].split("=", 1)[0].strip().strip('"')
            if key:
                elements.append(self._element(file_meta, key, StructuralKind.CONFIG_KEY, line_no, line_no))
        return ParsedFile(
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            language=file_meta.language or "",
            parser_name=parser_name,
            elements=elements or [self._fallback_element(file_meta)],
            confidence=0.65,
        )

    def _load_structured_config(self, rel_path, source):
        text = source or ""
        try:
            if rel_path.endswith(".json"):
                import json

                parsed = json.loads(text)
            elif rel_path.endswith(".toml"):
                import tomllib

                parsed = tomllib.loads(text)
            elif rel_path.endswith((".yaml", ".yml")):
                try:
                    import yaml
                except ImportError:
                    return None
                parsed = yaml.safe_load(text)
            else:
                return None
        except Exception as exc:
            logger.debug("structured config parse failed for %s: %s", rel_path, exc)
            return None
        return parsed if isinstance(parsed, dict) else {}

    def _config_key_elements(self, file_meta, data, prefix=""):
        # ponytail: line numbers unknown post-load; anchor nested keys at 1 until a line-preserving loader matters
        elements = []
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            elements.append(self._element(file_meta, path, StructuralKind.CONFIG_KEY, 1, 1))
            if isinstance(value, dict):
                elements.extend(self._config_key_elements(file_meta, value, path))
        return elements

    def _parse_generic(self, file_meta, source, parser_name):
        return ParsedFile(
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            language=file_meta.language or "",
            parser_name=parser_name,
            elements=[self._fallback_element(file_meta, source)],
            confidence=0.35,
        )

    def _binary_result(self, file_meta):
        return ParsedFile(
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            language=file_meta.language or "",
            parser_name="binary",
            elements=[self._fallback_element(file_meta)],
            confidence=0.2,
            metadata={"binary": True},
        )

    def _element(self, file_meta, name, kind, line_start, line_end, metadata=None):
        return StructuralElement(
            id=self._element_id(file_meta, kind.value, name, line_start),
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            name=name,
            kind=kind,
            line_start=line_start,
            line_end=line_end,
            metadata=metadata or {},
        )

    def _fallback_element(self, file_meta, source=""):
        return StructuralElement(
            id=self._element_id(file_meta, "text", file_meta.rel_path, 1),
            file_id=file_meta.id,
            file_path=file_meta.rel_path,
            name=file_meta.rel_path,
            kind=StructuralKind.TEXT_BLOCK,
            line_start=1,
            line_end=max(1, file_meta.lines_count),
            text=(source or "")[:500],
        )

    def _element_id(self, file_meta, kind, name, line):
        from astra.scanner.hash_engine import HashEngine

        return HashEngine().hash_string(f"{file_meta.id}:{kind}:{name}:{line}")

    def _read_text(self, file_meta):
        if file_meta.size_bytes > self._max_read_bytes:
            return ""
        encoding = file_meta.encoding or "utf-8"
        try:
            with open(file_meta.path, "r", encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_meta.path, "r", encoding="latin-1") as f:
                return f.read()

    def _parser_name(self, file_meta):
        if file_meta.is_binary:
            return "binary"
        return f"{file_meta.language or file_meta.category.value}_parser"

    def _import_target(self, node):
        if isinstance(node, ast.ImportFrom):
            return node.module or ""
        return ",".join(alias.name for alias in node.names)

    def _call_target(self, node):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return ""
