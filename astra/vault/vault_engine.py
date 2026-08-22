class VaultEngine:
    def extract_notes(self, parse_index):
        notes = []
        for parsed_file in parse_index.files:
            if parsed_file.language != "markdown":
                continue
            notes.append({
                "file_path": parsed_file.file_path,
                "headings": [e.name for e in parsed_file.elements if e.kind.value == "heading"],
                "links": [d.target for d in parsed_file.dependencies if d.signal_type == "links_to"],
            })
        return notes
