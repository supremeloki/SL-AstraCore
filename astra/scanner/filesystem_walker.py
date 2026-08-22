import os


class FilesystemWalker:
    def __init__(self, root_path, ignore_engine, follow_symlinks=False, include_hidden=True):
        self._root = os.path.abspath(root_path)
        self._ignore = ignore_engine
        self._follow_symlinks = follow_symlinks
        self._include_hidden = include_hidden

    def walk(self):
        visited_dirs = set()
        for dirpath, dirnames, filenames in os.walk(self._root, followlinks=self._follow_symlinks):
            dir_identity = self._dir_identity(dirpath)
            if dir_identity in visited_dirs:
                dirnames[:] = []
                continue
            visited_dirs.add(dir_identity)

            dirnames.sort()
            filenames.sort()
            rel_dir = os.path.relpath(dirpath, self._root)
            if rel_dir == ".":
                rel_dir = ""

            kept_dirs = []
            for dirname in dirnames:
                rel_path = self._join(rel_dir, dirname)
                if not self._include_hidden and self._is_hidden(dirname):
                    continue
                if self._ignore.is_ignored(rel_path) or self._ignore.is_ignored_dir(dirname):
                    continue
                if self._follow_symlinks:
                    child_identity = self._dir_identity(os.path.join(dirpath, dirname))
                    if child_identity in visited_dirs:
                        continue
                kept_dirs.append(dirname)
            dirnames[:] = kept_dirs

            yield {"type": "directory", "path": dirpath, "rel_path": rel_dir}

            for filename in filenames:
                rel_path = self._join(rel_dir, filename)
                if not self._include_hidden and self._is_hidden(filename):
                    continue
                if self._ignore.is_ignored(rel_path):
                    continue
                yield {"type": "file", "path": os.path.join(dirpath, filename), "rel_path": rel_path}

    def _join(self, rel_dir, name):
        return name if not rel_dir else os.path.join(rel_dir, name)

    def _is_hidden(self, name):
        return name.startswith(".")

    def _dir_identity(self, path):
        try:
            stat = os.stat(path)
            return (stat.st_dev, stat.st_ino)
        except OSError:
            return os.path.realpath(path)
