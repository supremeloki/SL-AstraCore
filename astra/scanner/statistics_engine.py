from astra.models.repository import LanguageSummary


class StatisticsEngine:
    def __init__(self):
        self._by_language = {}
        self._by_extension = {}
        self._binary_files = 0
        self._text_files = 0

    def record_file(self, file_metadata):
        language = file_metadata.language or "unknown"
        extension = file_metadata.extension or "<none>"
        self._by_language[language] = self._by_language.get(language, 0) + 1
        self._by_extension[extension] = self._by_extension.get(extension, 0) + 1
        if file_metadata.is_binary:
            self._binary_files += 1
        else:
            self._text_files += 1

    def summary(self):
        return LanguageSummary(
            by_language=dict(sorted(self._by_language.items())),
            by_extension=dict(sorted(self._by_extension.items())),
            binary_files=self._binary_files,
            text_files=self._text_files,
        )
