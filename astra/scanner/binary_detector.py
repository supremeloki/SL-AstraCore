class BinaryDetector:
    def __init__(self, sample_size=8192):
        self._sample_size = sample_size

    def is_binary(self, file_path):
        try:
            with open(file_path, "rb") as f:
                sample = f.read(self._sample_size)
        except OSError:
            return False
        if not sample:
            return False
        if b"\x00" in sample:
            return True
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(32, 127)))
        non_text = sample.translate(None, text_chars)
        return len(non_text) / len(sample) > 0.30
