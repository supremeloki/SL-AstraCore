from astra.core.logger import get_logger

logger = get_logger("astra.parser.tree_sitter_engine")


class TreeSitterEngine:
    def __init__(self):
        self._parsers = {}
        self._initialized = False

    def initialize(self, languages=None):
        try:
            import tree_sitter_languages
            langs = languages or [
                "python", "javascript", "typescript", "go", "rust",
                "java", "c", "cpp", "csharp", "ruby", "php",
            ]
            for lang in langs:
                try:
                    parser = tree_sitter_languages.get_parser(lang)
                    self._parsers[lang] = parser
                except Exception:
                    pass
            self._initialized = True
        except ImportError:
            logger.warning("tree-sitter-languages not installed, parsing disabled")
            self._initialized = False

    @property
    def is_available(self):
        return self._initialized

    def get_parser(self, language):
        return self._parsers.get(language)

    def supported_languages(self):
        return list(self._parsers.keys())

    def parse(self, source_code, language):
        parser = self._parsers.get(language)
        if parser is None:
            return None
        try:
            tree = parser.parse(bytes(source_code, "utf-8"))
            return tree
        except Exception as e:
            logger.error("Parse error for %s: %s", language, e)
            return None
