"""
Phase 1H — End-to-end integration test.

Verifies the entire Phase 1 pipeline on a synthetic FastAPI-like project:
  scan → parse → resolve imports → build graph → mutate → generate context pack

No network required. Uses in-memory fixtures.
"""
from __future__ import annotations


from astra.context.engine import ContextEngine
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.graph.mutator import GraphMutator
from astra.parser.python_adapter import PythonParserAdapter
from astra.parser.registry import ParserRegistry
from astra.resolver.import_resolver import resolve_imports_into_edges


# ── Synthetic FastAPI-like project ──────────────────────────────

MAIN_APP = '''
from fastapi import FastAPI
from fastapi.routing import APIRoute
from src.handlers import create_router
from src.models import Item

app = FastAPI()
app.router = create_router()
'''

HANDLERS = '''
from fastapi import APIRouter
from src.models import Item
from src.services import get_item, save_item

router = APIRouter()

@router.get("/items/{item_id}")
async def read_item(item_id: int):
    return get_item(item_id)

@router.post("/items")
async def create_item(item: Item):
    return save_item(item)
'''

MODELS = '''
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float

class Order(BaseModel):
    items: list[Item]
'''

SERVICES = '''
from src.models import Item

def get_item(item_id: int) -> Item:
    return Item(name="test", price=0.0)

def save_item(item: Item) -> Item:
    return item
'''

FILES = {
    "src/main.py": MAIN_APP,
    "src/handlers.py": HANDLERS,
    "src/models.py": MODELS,
    "src/services.py": SERVICES,
}


def test_e2e_full_pipeline():
    # ── Step 1: Parse all files ──────────────────────────────────
    registry = ParserRegistry()
    registry.register(PythonParserAdapter())

    parse_results = []
    for path, content in FILES.items():
        result = registry.parse(path, content)
        assert result is not None, f"Failed to parse {path}"
        parse_results.append(result)

    assert len(parse_results) == 4

    # Verify symbols extracted
    total_symbols = sum(len(r.symbols) for r in parse_results)
    assert total_symbols > 0, "No symbols extracted"

    # Verify dependencies extracted
    total_deps = sum(len(r.dependencies) for r in parse_results)
    assert total_deps > 0, "No dependencies extracted"

    # ── Step 2: Resolve imports into edges ──────────────────────
    resolved_map, dep_edges = resolve_imports_into_edges(parse_results)

    # At least some local imports should resolve
    resolved_count = sum(1 for v in resolved_map.values() if v)
    assert resolved_count > 0, "No imports resolved"

    # Should have edges for resolved imports
    assert len(dep_edges) > 0, "No dependency edges generated"

    # ── Step 3: Build graph via mutator ──────────────────────────
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    # Add file nodes
    for result in parse_results:
        if result.file_node:
            mutator.apply_node_upsert(result.file_node)

    # Add resolved edges (normalize to canonical file node ids)
    for edge in dep_edges:
        mutator.apply_edge_upsert(
            edge.__class__(
                from_node=f"file:{edge.from_node}",
                to_node=f"file:{edge.to_node}",
                type=edge.type,
                weight=edge.weight,
                confidence=edge.confidence,
                metadata=edge.metadata,
            )
        )

    all_nodes = storage.get_all_nodes()
    all_edges = storage.get_all_edges()

    assert len(all_nodes) == 4, f"Expected 4 nodes, got {len(all_nodes)}"
    assert len(all_edges) > 0, "No edges in graph"

    # ── Step 4: Generate context pack ───────────────────────────
    engine = ContextEngine(storage)

    # Start from main.py — should reach handlers via import edge
    pack = engine.generate_context_pack(
        query_intent="understand API entrypoint",
        seed_nodes=["file:src/main.py"],
    )

    assert len(pack.nodes) > 0, "Context pack is empty"
    assert len(pack.edges) > 0, "No edges in context pack"
    assert pack.confidence > 0.0

    # ── Step 5: Verify idempotency of mutation ──────────────────
    # Re-applying same nodes should produce zero adds
    for result in parse_results:
        if result.file_node:
            r = mutator.apply_node_upsert(result.file_node)
            assert r.added_nodes == 0, "Non-idempotent upsert detected"
            assert r.updated_nodes == 0, "False update detected"

    # ── Step 6: Verify incremental deletion ─────────────────────
    # Remove services.py node — should cascade its edges
    before_edges = len(storage.get_all_edges())
    mutator.apply_node_delete("file:src/services.py")

    after_edges = len(storage.get_all_edges())
    assert after_edges < before_edges, "Edge cascade deletion failed"
    assert storage.get_node("file:src/services.py") is None

    print("\n=== E2E Summary ===")
    print(f"Files parsed:  {len(parse_results)}")
    print(f"Symbols found: {total_symbols}")
    print(f"Dependencies:  {total_deps}")
    print(f"Edges resolved: {len(dep_edges)}")
    print(f"Graph nodes:   {len(all_nodes)}")
    print(f"Graph edges:   {len(all_edges)}")
    print(f"Context nodes: {len(pack.nodes)}")
    print(f"Context edges: {len(pack.edges)}")
    print(f"After deletion: {after_edges} edges remaining")
    print("=== Phase 1 E2E PASSED ===")
