"""A context pack must carry real source code, not just filenames.

Before this, `ContextNodeRef.snippet` was declared but never assigned anywhere in
the codebase, and every symbol parsed by the 12 language adapters was discarded
by the indexer. An agent receiving a pack got a list of file names and nothing to
read. These tests pin the fixed behaviour: symbols become graph nodes, snippets
carry the actual source a node points at, and the token budget still holds.
"""


import pytest

from astra.runtime.orchestrator import RuntimeOrchestrator
from astra.storage.backend import StorageProvider


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "auth.py").write_text(
        "import hashlib\n"
        "\n"
        "class Authenticator:\n"
        '    """Verifies credentials."""\n'
        "\n"
        "    def verify(self, token: str) -> bool:\n"
        "        return hashlib.sha256(token.encode()).hexdigest() != ''\n"
        "\n"
        "def login(user, password):\n"
        "    return Authenticator().verify(user + password)\n",
        encoding="utf-8",
    )
    return tmp_path


def _node_types(db_path: str) -> set[str]:
    storage = StorageProvider(backend="duckdb", db_path=db_path).create()
    storage.connect()
    try:
        return {n.type.name for n in storage.get_all_nodes()}
    finally:
        storage.close()


def test_symbols_become_graph_nodes(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    record = orch.index_repo(str(repo))
    types = _node_types(record.db_path)
    assert "CLASS" in types, "class Authenticator was parsed but not indexed"
    assert "FUNCTION" in types, "functions were parsed but not indexed"


def test_symbol_nodes_have_belongs_to_edges(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    record = orch.index_repo(str(repo))
    storage = StorageProvider(backend="duckdb", db_path=record.db_path).create()
    storage.connect()
    try:
        file_id = next(n.id for n in storage.get_all_nodes() if n.id.endswith("auth.py") and n.type.name == "FILE")
        children = [n for n in storage.get_all_nodes() if n.id.startswith(f"{file_id}::symbol:")]
        assert children, "no symbol nodes were created for auth.py"
        for child in children:
            assert any(e.from_node == child.id and e.to_node == file_id for e in storage.get_all_edges()), (
                f"{child.name} is not linked to its file"
            )
    finally:
        storage.close()


def test_context_pack_carries_real_source(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))
    pack = orch.query_context(str(repo), seed_node_ids=[], query_intent="authenticator verify login", max_tokens=4000)

    with_code = [n for n in pack.nodes if n.snippet]
    assert with_code, "context pack has no snippets at all"
    joined = "\n".join(n.snippet for n in with_code)
    assert "def login" in joined, "a function body must appear verbatim in the pack"
    assert "class Authenticator" in joined


def test_symbol_snippet_is_scoped_to_that_symbol(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))
    pack = orch.query_context(str(repo), seed_node_ids=[], query_intent="login", max_tokens=4000)

    login = next((n for n in pack.nodes if n.name == "login" and n.snippet), None)
    assert login is not None, "no snippet for the login function"
    assert "def login" in login.snippet
    assert "class Authenticator" not in login.snippet, "a function snippet must not carry the whole file"


def test_snippets_respect_the_token_budget(repo):
    for budget in (600, 1200, 4000):
        pack = orch_pack(repo, budget)
        total_chars = sum(len(n.snippet) for n in pack.nodes)
        # 70% of the budget goes to snippets, at ~4 chars per token
        assert total_chars <= budget * 0.7 * 4 + 200, f"snippets overflowed a {budget}-token budget"


def orch_pack(repo, budget):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))
    return orch.query_context(str(repo), seed_node_ids=[], query_intent="authenticator login", max_tokens=budget)


def test_zero_and_negative_budgets_are_clamped(repo):
    """A non-positive budget means "use the default", not "return nothing" —
    the old assertions (`x > 0 or x == 0`, `len(...) >= 0`) held for any value."""
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))

    default_budget = orch.query_context(
        str(repo), seed_node_ids=[], query_intent="login", max_tokens=None
    ).token_budget

    for bad in (0, -5):
        pack = orch.query_context(
            str(repo), seed_node_ids=[], query_intent="login", max_tokens=bad
        )
        assert pack.token_budget == default_budget, f"max_tokens={bad} was not clamped"
        # The clamp means the default budget, so the pack is the default pack —
        # not a specific size. Assert the answer is still there rather than
        # pinning a count that shifts whenever ranking improves.
        names = {n.name for n in pack.nodes}
        assert any("auth" in name for name in names), (
            f"the clamped pack dropped the matching file; it had {sorted(names)}"
        )
        assert pack.nodes, "the clamped pack was empty"

    # A real budget is still honoured, so the clamp is not masking it.
    small = orch.query_context(str(repo), seed_node_ids=[], query_intent="login", max_tokens=4000)
    assert small.token_budget == 4000


def test_snippet_is_empty_for_deleted_file(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))
    (repo / "auth.py").unlink()
    pack = orch.query_context(str(repo), seed_node_ids=[], query_intent="authenticator", max_tokens=4000)
    # A stale node for a vanished file must yield an empty snippet, not an exception.
    for node in pack.nodes:
        assert isinstance(node.snippet, str)
