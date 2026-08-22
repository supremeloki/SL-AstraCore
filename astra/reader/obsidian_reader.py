import os
import re
from astra.core.logger import get_logger
from astra.models.vault_node import VaultNode

logger = get_logger("astra.reader.obsidian_reader")


class ObsidianReader:
    def __init__(self):
        self._frontmatter_re = re.compile(
            r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL
        )
        self._wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
        self._tag_re = re.compile(r"(?:^|\s)#([A-Za-z0-9_/-]+)")
        self._callout_re = re.compile(r"^>\s*\[!([^\]]+)\]\s*(.*)$")
        self._embed_re = re.compile(r"!\[\[([^\]]+)\]\]")

    def read(self, file_path, encoding="utf-8"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
        except Exception as e:
            logger.error("Failed to read vault note %s: %s", file_path, e)
            return None
        vault_node = VaultNode(
            file_path=file_path,
            title=self._extract_title(file_path, content),
            content=content,
            frontmatter=self._extract_frontmatter(content),
            wikilinks=self._extract_wikilinks(content),
            tags=self._extract_tags(content),
        )
        vault_node.is_daily_note = self._detect_daily(file_path)
        vault_node.is_template = self._detect_template(file_path)
        vault_node.concepts = self._extract_concepts(content)
        vault_node.decisions = self._extract_decisions(content)
        vault_node.architecture_notes = self._extract_architecture_notes(content)
        vault_node.linked_code_modules = self._extract_code_links(content)
        return vault_node

    def _extract_title(self, file_path, content):
        stem = os.path.splitext(os.path.basename(file_path))[0]
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# ") and not line.startswith("## "):
                return line[2:].strip()
            if line and not line.startswith("---"):
                break
        return stem

    def _extract_frontmatter(self, content):
        match = self._frontmatter_re.match(content)
        if not match:
            return {}
        fm = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                fm[key.strip()] = value.strip().strip("\"'")
        return fm

    def _extract_wikilinks(self, content):
        links = []
        for match in self._wikilink_re.finditer(content):
            target = match.group(1).strip()
            alias = match.group(2)
            links.append({
                "target": target,
                "alias": alias.strip() if alias else None,
                "line": content[:match.start()].count("\n") + 1,
            })
        return links

    def _extract_tags(self, content):
        tags = set()
        for match in self._tag_re.finditer(content):
            tags.add(match.group(1))
        return sorted(tags)

    def _extract_concepts(self, content):
        concepts = []
        headings = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
        concept_keywords = ["concept", "idea", "principle", "pattern", "model", "theory"]
        lower = content.lower()
        for heading in headings:
            if any(kw in heading.lower() for kw in concept_keywords):
                concepts.append(heading.strip())
        return concepts

    def _extract_decisions(self, content):
        decisions = []
        for match in re.finditer(r"^##\s*(?:ADR|Decision)[\s:.-]*(.+)$", content, re.MULTILINE | re.IGNORECASE):
            decisions.append(match.group(1).strip())
        return decisions

    def _extract_architecture_notes(self, content):
        notes = []
        arch_keywords = ["architecture", "design", "structure", "layer", "module", "component"]
        for match in re.finditer(r"^##\s*(.+)$", content, re.MULTILINE):
            heading = match.group(1)
            if any(kw in heading.lower() for kw in arch_keywords):
                notes.append(heading.strip())
        return notes

    def _extract_code_links(self, content):
        code_refs = re.findall(r"```[\w]*\s*(?://\s*)?(?:file:\s*)?([^\n]+)", content)
        return [ref.strip() for ref in code_refs if ref.strip()]

    def _detect_daily(self, file_path):
        stem = os.path.basename(file_path)
        return bool(re.match(r"\d{4}-\d{2}-\d{2}", stem))

    def _detect_template(self, file_path):
        return "/templates/" in file_path.replace("\\", "/")
