from __future__ import annotations

from pathlib import Path

from codectx.contexting import ContextingError, ContextResult, build_context
from codectx.frontends.base import ChunkFact, NodeFact
from codectx.graph.store import GraphStore
from codectx.scanner.models import FileRecord
from codectx.source.spans import SourceSpan


def test_build_context_returns_markdown_for_file_line_anchor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo)

    result = build_context(
        repo,
        db_path=db_path,
        file_path="src/Foo.java",
        line=2,
        goal="explain",
        output_format="markdown",
    )

    assert isinstance(result, ContextResult)
    assert "# codectx context bundle" in result.rendered_text
    assert "target.definition" in result.rendered_text
    assert "src/Foo.java:1-3" in result.rendered_text
    assert result.output_path is None


def test_build_context_returns_json_and_text_for_symbol_anchor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo)

    json_result = build_context(
        repo, db_path=db_path, symbol="Foo", output_format="json"
    )
    text_result = build_context(
        repo, db_path=db_path, symbol="Foo", output_format="text"
    )

    assert isinstance(json_result, ContextResult)
    assert '"goal": "explain"' in json_result.rendered_text
    assert isinstance(text_result, ContextResult)
    assert text_result.rendered_text.startswith("codectx context bundle\n")


def test_build_context_records_ambiguous_symbol_note(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo, include_second_symbol=True)

    result = build_context(repo, db_path=db_path, symbol="Foo")

    assert isinstance(result, ContextResult)
    assert "Symbol query matched 2 symbols" in result.rendered_text


def test_build_context_preserves_selected_symbol_anchor_on_shared_line(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo, include_same_line_callable=True)

    result = build_context(repo, db_path=db_path, symbol="Foo", output_format="json")

    assert isinstance(result, ContextResult)
    assert '"node_id": 1' in result.rendered_text
    assert '"node_name": "Foo"' in result.rendered_text
    assert '"qualified_name": "Foo"' in result.rendered_text


def test_build_context_validates_goal_format_and_budget(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    bad_goal = build_context(repo, symbol="PaymentService", goal="unknown")
    bad_format = build_context(repo, symbol="PaymentService", output_format="unknown")
    bad_budget = build_context(repo, symbol="PaymentService", budget=0)

    assert isinstance(bad_goal, ContextingError)
    assert "Unsupported context goal" in bad_goal.message
    assert isinstance(bad_format, ContextingError)
    assert "Unsupported context format" in bad_format.message
    assert isinstance(bad_budget, ContextingError)
    assert "budget" in bad_budget.message


def test_build_context_validates_anchor_shape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    missing_anchor = build_context(repo)
    duplicate_anchor = build_context(
        repo, symbol="PaymentService", file_path="src/Foo.java"
    )

    assert isinstance(missing_anchor, ContextingError)
    assert "Provide either --symbol or --file" in missing_anchor.message
    assert isinstance(duplicate_anchor, ContextingError)
    assert "Provide only one context anchor" in duplicate_anchor.message


def test_build_context_validates_file_line_anchor_shape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    missing_line = build_context(repo, file_path="src/Foo.java")
    bad_line = build_context(repo, file_path="src/Foo.java", line=0)
    symbol_with_line = build_context(repo, symbol="PaymentService", line=10)

    assert isinstance(missing_line, ContextingError)
    assert "--line is required" in missing_line.message
    assert isinstance(bad_line, ContextingError)
    assert "Line number must be 1 or greater" in bad_line.message
    assert isinstance(symbol_with_line, ContextingError)
    assert "--line can only be used with --file" in symbol_with_line.message


def test_build_context_validates_and_resolves_output_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo)
    output_path = tmp_path / "context.md"

    result = build_context(repo, db_path=db_path, symbol="Foo", output_path=output_path)
    missing_parent = build_context(
        repo,
        symbol="PaymentService",
        output_path=tmp_path / "missing" / "context.md",
    )

    assert isinstance(result, ContextResult)
    assert result.output_path == output_path.resolve()
    assert isinstance(missing_parent, ContextingError)
    assert "Output directory does not exist" in missing_parent.message


def test_build_context_reports_missing_index_and_missing_symbol(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    missing_index = build_context(
        repo,
        symbol="Foo",
        db_path=tmp_path / "missing.sqlite",
    )
    assert isinstance(missing_index, ContextingError)
    assert "No codectx index found" in missing_index.message

    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo)
    missing_symbol = build_context(repo, db_path=db_path, symbol="Missing")
    assert isinstance(missing_symbol, ContextingError)
    assert "No symbols found for Missing" in missing_symbol.message


def test_build_context_reports_db_without_snapshot_and_snapshot_without_stats(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        store.apply_schema()

    no_snapshot = build_context(repo, db_path=db_path, symbol="Foo")

    with GraphStore(db_path) as store:
        repo_id = store.create_repo(repo)
        store.create_snapshot(repo_id)

    no_stats = build_context(repo, db_path=db_path, symbol="Foo")

    assert isinstance(no_snapshot, ContextingError)
    assert f"No codectx index found for {repo.resolve()}" in no_snapshot.message
    assert isinstance(no_stats, ContextingError)
    assert "No index health stats found" in no_stats.message


def test_build_context_reports_missing_file_and_absolute_file_outside_repo(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo)

    missing_file = build_context(
        repo,
        db_path=db_path,
        file_path="src/Missing.java",
        line=1,
    )
    outside_file = build_context(
        repo,
        db_path=db_path,
        file_path=tmp_path / "outside.java",
        line=1,
    )

    assert isinstance(missing_file, ContextingError)
    assert "File is not indexed" in missing_file.message
    assert isinstance(outside_file, ContextingError)
    assert "File is not indexed" in outside_file.message


def test_build_context_routes_non_explain_goals_through_shared_planner(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    db_path = tmp_path / "graph.sqlite"
    with GraphStore(db_path) as store:
        _seed_context_graph(store, repo)

    result = build_context(
        repo,
        db_path=db_path,
        symbol="Foo",
        goal="dependencies",
        output_format="json",
    )

    assert isinstance(result, ContextResult)
    assert '"goal": "dependencies"' in result.rendered_text
    assert "target.definition" in result.rendered_text


def _seed_context_graph(
    store: GraphStore,
    repo: Path,
    *,
    include_second_symbol: bool = False,
    include_same_line_callable: bool = False,
) -> int:
    source = "class Foo {\n  void run() {}\n}\n"
    _write(repo / "src" / "Foo.java", source)
    store.apply_schema()
    repo_id = store.create_repo(repo)
    snapshot_id = store.create_snapshot(repo_id)
    file_ids = store.insert_files(
        snapshot_id,
        [
            FileRecord(
                path="src/Foo.java",
                language="java",
                content_hash="abc123",
                size_bytes=len(source.encode("utf-8")),
                line_count=3,
            )
        ],
    )
    nodes = [
        NodeFact(
            kind="type",
            language="java",
            name="Foo",
            qualified_name="Foo",
            symbol_key="java:src/Foo.java#Foo",
            file_path="src/Foo.java",
            span=SourceSpan(
                file_path="src/Foo.java",
                start_byte=0,
                end_byte=len(source.encode("utf-8")),
                start_line=1,
                start_col=0,
                end_line=3,
                end_col=1,
            ),
            confidence=1.0,
            extractor="test",
            metadata={},
        )
    ]
    if include_second_symbol:
        nodes.append(
            NodeFact(
                kind="type",
                language="java",
                name="FooHelper",
                qualified_name="FooHelper",
                symbol_key="java:src/Foo.java#FooHelper",
                file_path="src/Foo.java",
                span=SourceSpan(
                    file_path="src/Foo.java",
                    start_byte=0,
                    end_byte=len(source.encode("utf-8")),
                    start_line=1,
                    start_col=0,
                    end_line=3,
                    end_col=1,
                ),
                confidence=1.0,
                extractor="test",
                metadata={},
            )
        )
    if include_same_line_callable:
        nodes.append(
            NodeFact(
                kind="callable",
                language="java",
                name="run",
                qualified_name="Foo.run()",
                symbol_key="java:src/Foo.java#run",
                file_path="src/Foo.java",
                span=SourceSpan(
                    file_path="src/Foo.java",
                    start_byte=0,
                    end_byte=len(source.encode("utf-8")),
                    start_line=1,
                    start_col=0,
                    end_line=1,
                    end_col=29,
                ),
                confidence=1.0,
                extractor="test",
                metadata={},
            )
        )
    node_ids = store.insert_nodes(snapshot_id, nodes, file_ids)
    store.insert_chunks(
        [
            ChunkFact(
                file_path="src/Foo.java",
                node_key="java:src/Foo.java#Foo",
                kind="definition",
                start_line=1,
                end_line=3,
                text=source,
                token_estimate=8,
            )
        ],
        file_ids,
        node_ids,
    )
    store.upsert_index_stats(snapshot_id, {"files": "1", "nodes": "1"})
    return snapshot_id


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
