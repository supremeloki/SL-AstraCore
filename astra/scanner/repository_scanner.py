import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from astra.core.constants import FILE_CATEGORY_MAP, MAX_FILE_SIZE_KB
from astra.core.logger import get_logger
from astra.models.file_node import FileCategory
from astra.models.repository import (
    RepositoryIndex,
    RepositoryTree,
    ScanFailure,
    ScanMetadata,
    TreeNode,
)
from astra.scanner.binary_detector import BinaryDetector
from astra.scanner.checkpoint_engine import CheckpointEngine
from astra.scanner.export_engine import ExportEngine
from astra.scanner.filesystem_walker import FilesystemWalker
from astra.scanner.hash_engine import HashEngine
from astra.scanner.ignore_engine import IgnoreEngine
from astra.scanner.language_detector import LanguageDetector
from astra.scanner.metadata_extractor import MetadataExtractor
from astra.scanner.statistics_engine import StatisticsEngine

logger = get_logger("astra.scanner.repository_scanner")


class RepositoryScanner:
    def __init__(self, root_path, config=None):
        self._root = os.path.abspath(root_path)
        self._config = config
        self._max_size = self._cfg("scanner.max_file_size_kb", MAX_FILE_SIZE_KB)
        self._follow_symlinks = self._cfg("scanner.follow_symlinks", False)
        self._include_hidden = self._cfg("scanner.include_hidden", True)
        self._hash_algorithm = self._cfg("scanner.hash_algorithm", "sha256")
        self._streaming_buffer = int(self._cfg("scanner.streaming_buffer", 65536))
        self._checkpoint_path = self._cfg("scanner.checkpoint_path", "")
        self._checkpoint_every = self._cfg("scanner.checkpoint_every", 1000)
        self._worker_count = max(1, int(self._cfg("scanner.worker_count", 1)))
        self._respect_astraignore = bool(self._cfg("scanner.respect_astraignore", True))

        self._ignore = IgnoreEngine(self._root, respect_astraignore=self._respect_astraignore)
        self._detector = LanguageDetector()
        self._binary = BinaryDetector()
        self._hasher = HashEngine(self._hash_algorithm, self._streaming_buffer)
        self._metadata = MetadataExtractor(
            self._root,
            self._detector,
            self._binary,
            self._hasher,
            self._max_size,
            self._hash_algorithm,
        )
        self._walker = FilesystemWalker(
            self._root,
            self._ignore,
            follow_symlinks=self._follow_symlinks,
            include_hidden=self._include_hidden,
        )
        self._checkpoint = CheckpointEngine(self._checkpoint_path, self._checkpoint_every)
        self._export = ExportEngine()

    def scan_iter(self, resume=False):
        if resume:
            self._checkpoint.load_state()
        indexed_count = 0
        pending = deque()
        max_pending = max(1, self._worker_count * 2)

        with ThreadPoolExecutor(max_workers=self._worker_count) as executor:
            for event in self._walker.walk():
                if event["type"] != "file":
                    continue
                rel_path = self._normalize_rel(event["rel_path"])
                pending.append((rel_path, executor.submit(self._build_file_metadata, event["path"], rel_path)))
                if len(pending) >= max_pending:
                    item = self._consume_pending(pending)
                    if isinstance(item, ScanFailure):
                        yield item
                    elif resume and self._checkpoint.is_unchanged(item):
                        self._checkpoint.mark_file(item, indexed_count)
                    else:
                        indexed_count += 1
                        self._checkpoint.mark_file(item, indexed_count)
                        yield item

            while pending:
                item = self._consume_pending(pending)
                if isinstance(item, ScanFailure):
                    yield item
                elif resume and self._checkpoint.is_unchanged(item):
                    self._checkpoint.mark_file(item, indexed_count)
                else:
                    indexed_count += 1
                    self._checkpoint.mark_file(item, indexed_count)
                    yield item
        self._checkpoint.save()

    def scan_repository(self, resume=False):
        files = []
        failures = []
        stats = StatisticsEngine()
        tree = RepositoryTree(root=self._root)
        metadata = ScanMetadata(
            root_path=self._root,
            checkpoint_path=self._checkpoint_path,
            resumed=resume,
        )
        if resume:
            self._checkpoint.load_state()
        current_paths = set()
        resume_stats = {
            "skipped_unchanged": 0,
            "changed_paths": [],
        }
        pending = deque()
        indexed_count = 0
        max_pending = max(1, self._worker_count * 2)

        with ThreadPoolExecutor(max_workers=self._worker_count) as executor:
            for event in self._walker.walk():
                if event["type"] == "directory":
                    metadata.directories_seen += 1
                    self._record_tree_dir(tree, event["rel_path"])
                    continue

                metadata.files_seen += 1
                rel_path = self._normalize_rel(event["rel_path"])
                current_paths.add(rel_path)
                pending.append((rel_path, executor.submit(self._build_file_metadata, event["path"], rel_path)))
                if len(pending) >= max_pending:
                    indexed_count = self._record_scan_item(
                        self._consume_pending(pending),
                        files,
                        failures,
                        stats,
                        tree,
                        metadata,
                        indexed_count,
                        resume,
                        resume_stats,
                    )

            while pending:
                indexed_count = self._record_scan_item(
                    self._consume_pending(pending),
                    files,
                    failures,
                    stats,
                    tree,
                    metadata,
                    indexed_count,
                    resume,
                    resume_stats,
                )
        deleted_paths = self._checkpoint.deleted_paths(current_paths) if resume else []
        if resume:
            self._checkpoint.retain_only(current_paths)
        self._checkpoint.save()

        metadata.metadata = {
            "hash_algorithm": self._hash_algorithm,
            "follow_symlinks": self._follow_symlinks,
            "include_hidden": self._include_hidden,
            "max_file_size_kb": self._max_size,
            "worker_count": self._worker_count,
            "streaming_buffer": self._streaming_buffer,
            "skipped_unchanged": resume_stats["skipped_unchanged"],
            "changed_paths": resume_stats["changed_paths"],
            "deleted_paths": deleted_paths,
        }
        return RepositoryIndex(
            root_path=self._root,
            files=files,
            tree=tree,
            language_summary=stats.summary(),
            metadata=metadata,
            failures=failures,
        )

    def _record_scan_item(self, item, files, failures, stats, tree, metadata, indexed_count, resume=False, resume_stats=None):
        if isinstance(item, ScanFailure):
            metadata.failures_count += 1
            if "exceeds max_file_size_kb" in item.error:
                metadata.skipped_large_files += 1
            failures.append(item)
            return indexed_count

        if resume and self._checkpoint.is_unchanged(item):
            if resume_stats is not None:
                resume_stats["skipped_unchanged"] += 1
            self._checkpoint.mark_file(item, indexed_count)
            return indexed_count

        metadata.files_indexed += 1
        stats.record_file(item)
        self._record_tree_file(tree, item)
        files.append(item)
        indexed_count += 1
        if resume and resume_stats is not None:
            resume_stats["changed_paths"].append(item.rel_path)
        self._checkpoint.mark_file(item, indexed_count)
        return indexed_count

    def scan(self):
        return self.scan_repository().to_file_nodes()

    def export_json(self, output_path, resume=False):
        repo_index = self.scan_repository(resume=resume)
        self._export.write_json(repo_index, output_path)
        return repo_index

    def export_jsonl(self, output_path, resume=False):
        self._export.write_jsonl(self.scan_iter(resume=resume), output_path)
        return output_path

    def _build_file_metadata(self, full_path, rel_path):
        try:
            ext = os.path.splitext(rel_path)[1].lower()
            language = self._detector.detect(rel_path)
            category = self._classify(ext, language)
            return self._metadata.extract(full_path, rel_path, category)
        except PermissionError as exc:
            return None, f"permission denied: {exc}"
        except OSError as exc:
            return None, str(exc)

    def _consume_pending(self, pending):
        rel_path, future = pending.popleft()
        file_meta, error = future.result()
        if error:
            return ScanFailure(path=rel_path, phase="metadata", error=error)
        return file_meta

    def _classify(self, ext, language):
        if ext in FILE_CATEGORY_MAP.get("source", set()):
            return FileCategory.SOURCE
        if ext in FILE_CATEGORY_MAP.get("knowledge", set()):
            return FileCategory.KNOWLEDGE
        if ext in FILE_CATEGORY_MAP.get("config", set()):
            return FileCategory.CONFIG
        if ext in FILE_CATEGORY_MAP.get("data", set()):
            return FileCategory.DATA
        if ext in FILE_CATEGORY_MAP.get("document", set()):
            return FileCategory.DOCUMENT
        if ext in FILE_CATEGORY_MAP.get("asset", set()):
            return FileCategory.ASSET
        if ext in FILE_CATEGORY_MAP.get("system", set()):
            return FileCategory.SYSTEM
        if language:
            return FileCategory.SOURCE
        return FileCategory.UNKNOWN

    def _record_tree_dir(self, tree, rel_path):
        rel_path = self._normalize_rel(rel_path)
        key = rel_path or "."
        tree.nodes.setdefault(key, TreeNode(path=rel_path, name=os.path.basename(rel_path) or ".", node_type="directory"))

    def _record_tree_file(self, tree, file_meta):
        rel_path = self._normalize_rel(file_meta.rel_path)
        tree.nodes[rel_path] = TreeNode(
            path=rel_path,
            name=file_meta.name,
            node_type="file",
            file_id=file_meta.id,
        )
        parent = os.path.dirname(rel_path).replace("\\", "/")
        parent_key = parent or "."
        parent_node = tree.nodes.setdefault(
            parent_key,
            TreeNode(path=parent, name=os.path.basename(parent) or ".", node_type="directory"),
        )
        if rel_path not in parent_node.children:
            parent_node.children.append(rel_path)
            parent_node.children.sort()

    def _normalize_rel(self, rel_path):
        if not rel_path or rel_path == ".":
            return ""
        return rel_path.replace("\\", "/")

    def _cfg(self, key, default):
        if self._config is None:
            return default
        return self._config.get(key, default)
