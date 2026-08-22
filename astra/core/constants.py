import os

ROOT_DIR = os.getcwd()
ASTRA_DIR = os.path.join(ROOT_DIR, ".astra")
ASTRAIGNORE_PATH = os.path.join(ROOT_DIR, ".astraignore")
CONFIG_PATH = os.path.join(ROOT_DIR, "astra.yaml")

DEFAULT_IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", "dist", "build",
    ".venv", "venv", "env", ".mypy_cache", ".ruff_cache",
    ".eggs", "*.egg-info", ".tox", ".nox", "htmlcov",
    ".coverage", ".pytest_cache", ".astra",
}

DEFAULT_IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll",
    ".exe", ".bin", ".wasm", ".lock",
}

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "shell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "css",
    ".less": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".rst": "markdown",
    ".txt": "text",
    ".csv": "data",
    ".env": "env",
    ".dockerfile": "docker",
    ".tf": "terraform",
    ".proto": "protobuf",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".cc",
    ".cxx", ".hpp", ".cs", ".rb", ".php", ".r", ".R",
    ".lua", ".sh", ".bash", ".zsh", ".ps1", ".sql",
    ".html", ".css", ".scss", ".less",
}

MARKDOWN_EXTENSIONS = {".md", ".rst", ".mdx"}

CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".xml", ".env"}

DATA_EXTENSIONS = {".sql", ".csv"}

DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".rtf"}

ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".bmp", ".tiff", ".avif",
}

SYSTEM_EXTENSIONS = {
    ".dockerfile", ".sh", ".bash", ".zsh", ".ps1",
    ".tf", ".proto",
}

FILE_CATEGORY_MAP = {
    "source": SOURCE_EXTENSIONS,
    "knowledge": MARKDOWN_EXTENSIONS,
    "config": CONFIG_EXTENSIONS,
    "data": DATA_EXTENSIONS,
    "document": DOCUMENT_EXTENSIONS,
    "asset": ASSET_EXTENSIONS,
    "system": SYSTEM_EXTENSIONS,
}

MAX_FILE_SIZE_KB = 1024
MAX_LINES_PER_FILE = 250000

STATUS_UNREAD = "unread"
STATUS_READING = "reading"
STATUS_READ = "read"
STATUS_PARSED = "parsed"
STATUS_INDEXED = "indexed"
STATUS_ERROR = "error"
