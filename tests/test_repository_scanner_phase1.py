import json
import os
import tempfile
import unittest

from astra.models.file_node import FileCategory
from astra.models.repository import FileKind, RepositoryIndex
from astra.scanner import RepositoryScanner
from astra.storage import RepositoryIndexStore


class ScannerConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


class RepositoryScannerPhase1Tests(unittest.TestCase):
    def test_scan_repository_builds_contract(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "src/app.py", "print('ok')\n")
            self._write(root, "README.md", "# Project\n")
            self._write_bytes(root, "assets/logo.png", b"\x89PNG\x00\x00")
            self._write(root, ".astraignore", "ignored\n")
            self._write(root, "ignored/skip.py", "print('skip')\n")

            repo_index = RepositoryScanner(root, ScannerConfig({"scanner.worker_count": 2})).scan_repository()

            self.assertIsInstance(repo_index, RepositoryIndex)
            paths = [f.rel_path for f in repo_index.files]
            self.assertEqual(paths, [".astraignore", "README.md", "assets/logo.png", "src/app.py"])
            self.assertEqual(repo_index.metadata.files_indexed, 4)
            self.assertIn("python", repo_index.language_summary.by_language)
            self.assertIn("markdown", repo_index.language_summary.by_language)
            self.assertEqual(repo_index.language_summary.binary_files, 1)

            app = next(f for f in repo_index.files if f.rel_path == "src/app.py")
            self.assertEqual(app.category, FileCategory.SOURCE)
            self.assertEqual(app.kind, FileKind.TEXT)
            self.assertEqual(app.id, repo_index.files[-1].id)
            self.assertTrue(app.hash_value)

            asset = next(f for f in repo_index.files if f.rel_path == "assets/logo.png")
            self.assertEqual(asset.category, FileCategory.ASSET)
            self.assertTrue(asset.is_binary)

    def test_export_json_and_resume_checkpoint(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out_dir:
            self._write(root, "a.py", "A = 1\n")
            checkpoint = os.path.join(root, ".astra", "scan.checkpoint.json")
            output = os.path.join(out_dir, "scan.json")
            config = ScannerConfig({
                "scanner.checkpoint_path": checkpoint,
                "scanner.checkpoint_every": 1,
            })

            scanner = RepositoryScanner(root, config)
            first = scanner.export_json(output)
            second = scanner.scan_repository(resume=True)

            self.assertEqual(first.metadata.files_indexed, 1)
            self.assertTrue(os.path.exists(output))
            self.assertTrue(os.path.exists(checkpoint))
            self.assertEqual(second.metadata.files_indexed, 0)
            self.assertEqual(second.metadata.metadata["skipped_unchanged"], 1)
            with open(output, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("files", data)
            self.assertEqual(data["files"][0]["rel_path"], "a.py")

    def test_resume_tracks_changed_deleted_and_unchanged_files(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "changed.py", "VALUE = 1\n")
            self._write(root, "deleted.py", "DELETE_ME = True\n")
            self._write(root, "unchanged.py", "UNCHANGED = True\n")
            checkpoint = os.path.join(root, ".astra", "scan.checkpoint.json")
            config = ScannerConfig({
                "scanner.checkpoint_path": checkpoint,
                "scanner.checkpoint_every": 1,
            })

            RepositoryScanner(root, config).scan_repository()
            self._write(root, "changed.py", "VALUE = 2\n")
            self._write(root, "added.py", "ADDED = True\n")
            os.remove(os.path.join(root, "deleted.py"))

            resumed = RepositoryScanner(root, config).scan_repository(resume=True)
            resumed_paths = [file.rel_path for file in resumed.files]

            self.assertEqual(resumed_paths, ["added.py", "changed.py"])
            self.assertEqual(resumed.metadata.files_indexed, 2)
            self.assertEqual(resumed.metadata.metadata["skipped_unchanged"], 1)
            self.assertEqual(resumed.metadata.metadata["deleted_paths"], ["deleted.py"])
            self.assertEqual(resumed.metadata.metadata["changed_paths"], ["added.py", "changed.py"])

            unchanged_resume = RepositoryScanner(root, config).scan_repository(resume=True)

            self.assertEqual(unchanged_resume.metadata.files_indexed, 0)
            self.assertEqual(unchanged_resume.metadata.metadata["skipped_unchanged"], 3)

    def test_repository_index_store_persists_index(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out_dir:
            self._write(root, "main.py", "print('ok')\n")
            index = RepositoryScanner(root).scan_repository()
            store = RepositoryIndexStore(os.path.join(out_dir, "repository-index.json"))

            store.save(index)
            loaded = store.load_dict()

            self.assertTrue(store.exists())
            self.assertEqual(loaded["root_path"], os.path.abspath(root))
            self.assertEqual(loaded["files"][0]["rel_path"], "main.py")

    def test_streaming_scan_handles_many_files_deterministically(self):
        with tempfile.TemporaryDirectory() as root:
            for index in range(300):
                self._write(root, f"pkg/module_{index:03d}.py", f"VALUE = {index}\n")

            scanner = RepositoryScanner(root, ScannerConfig({"scanner.worker_count": 4}))
            paths = [
                item.rel_path
                for item in scanner.scan_iter()
                if not isinstance(item, tuple)
            ]

            self.assertEqual(len(paths), 300)
            self.assertEqual(paths[0], "pkg/module_000.py")
            self.assertEqual(paths[-1], "pkg/module_299.py")

    def test_follow_symlinks_protects_against_directory_cycles(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "main.py", "print('ok')\n")
            loop_path = os.path.join(root, "loop")
            try:
                os.symlink(root, loop_path, target_is_directory=True)
            except (AttributeError, NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation is not available: {exc}")

            config = ScannerConfig({"scanner.follow_symlinks": True})
            repo_index = RepositoryScanner(root, config).scan_repository()

            self.assertEqual([file.rel_path for file in repo_index.files], ["main.py"])
            self.assertLess(repo_index.metadata.directories_seen, 5)

    def test_legacy_scan_returns_file_nodes(self):
        with tempfile.TemporaryDirectory() as root:
            self._write(root, "main.py", "print('ok')\n")

            nodes = RepositoryScanner(root).scan()

            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0].rel_path, "main.py")
            self.assertEqual(nodes[0].metadata["kind"], "text")

    def test_jsonl_export_streams_files(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out_dir:
            self._write(root, "a.py", "A = 1\n")
            self._write(root, "b.md", "# B\n")
            output = os.path.join(out_dir, "scan.jsonl")

            RepositoryScanner(root).export_jsonl(output)

            with open(output, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            self.assertEqual([line["rel_path"] for line in lines], ["a.py", "b.md"])

    def _write(self, root, rel_path, content):
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _write_bytes(self, root, rel_path, content):
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)


if __name__ == "__main__":
    unittest.main()
