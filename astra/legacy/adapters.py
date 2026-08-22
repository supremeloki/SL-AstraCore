from astra.ir.models import IRProjectIndex, IRFileNode
from astra.models.project_index import ProjectIndex

def to_legacy_project_index(ir_repo_index) -> ProjectIndex:
    index = ProjectIndex(files=[IRFileNode(
        id=f.id,
        type=f.type,
        name=f.name,
        source=f.source,
        file_path=f.file_path
    ) for f in ir_repo_index.files])
    index.metadata = {
        "repository_index": ir_repo_index,
        "repository_scan": ir_repo_index.metadata,
        "language_summary": ir_repo_index.language_summary,
        "failure_report": ir_repo_index.failures,
    }
    return index
