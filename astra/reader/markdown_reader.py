import re
from astra.core.logger import get_logger

logger = get_logger("astra.reader.markdown_reader")


class MarkdownReader:
    def __init__(self):
        self._heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
        self._codeblock_re = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        self._link_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        self._list_re = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.+)$")
        self._bold_re = re.compile(r"\*\*(.+?)\*\*")
        self._italic_re = re.compile(r"\*(.+?)\*")

    def read(self, file_path, encoding="utf-8"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
        except Exception as e:
            logger.error("Failed to read markdown %s: %s", file_path, e)
            return None
        return {
            "file_path": file_path,
            "content": content,
            "headings": self._extract_headings(content),
            "code_blocks": self._extract_code_blocks(content),
            "links": self._extract_links(content),
            "list_items": self._extract_lists(content),
            "line_count": content.count("\n") + 1,
        }

    def _extract_headings(self, content):
        headings = []
        for match in self._heading_re.finditer(content):
            headings.append({
                "level": len(match.group(1)),
                "text": match.group(2).strip(),
                "line": content[:match.start()].count("\n") + 1,
            })
        return headings

    def _extract_code_blocks(self, content):
        blocks = []
        for match in self._codeblock_re.finditer(content):
            blocks.append({
                "language": match.group(1) or "text",
                "code": match.group(2),
                "line": content[:match.start()].count("\n") + 1,
            })
        return blocks

    def _extract_links(self, content):
        links = []
        for match in self._link_re.finditer(content):
            links.append({
                "text": match.group(1),
                "url": match.group(2),
                "line": content[:match.start()].count("\n") + 1,
            })
        return links

    def _extract_lists(self, content):
        items = []
        for match in self._list_re.finditer(content):
            items.append({
                "indent": len(match.group(1)),
                "marker": match.group(2),
                "text": match.group(3).strip(),
                "line": content[:match.start()].count("\n") + 1,
            })
        return items
