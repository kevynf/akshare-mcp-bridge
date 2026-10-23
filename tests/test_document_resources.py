"""Tests for documentation chunks exposed as MCP resources."""

from __future__ import annotations

from typing import Any

from akbridge.catalog import ApiFunction, signature_to_schema
from akbridge.router import DOC_URI_PREFIX, CatalogIndex, document_uri


def _api(name: str) -> ApiFunction:
    def fn() -> dict[str, Any]:
        return {}

    return ApiFunction(
        name=name,
        function=fn,
        description=name,
        input_schema=signature_to_schema(fn),
        signature="() -> dict",
        category="macro",
    )


def _chunk(chunk_id: str, api_names: list[str], text: str = "body") -> dict[str, Any]:
    return {
        "id": chunk_id,
        "title": f"Doc {chunk_id}",
        "path": f"data/macro/{chunk_id}.md",
        "source_url": f"https://example.test/{chunk_id}",
        "text": text,
        "api_names": api_names,
        "categories": ["macro"],
    }


def test_chunks_are_indexed_and_addressable_by_uri() -> None:
    catalog = {"macro_china_cpi": _api("macro_china_cpi")}
    index = CatalogIndex(
        catalog,
        documents=[
            _chunk("cpi.md:1", ["macro_china_cpi"], text="中国 CPI 数据说明"),
            _chunk("cpi.md:2", ["macro_china_cpi"], text="更多细节"),
        ],
    )
    chunks = index.document_chunks()
    assert [chunk["id"] for chunk in chunks] == ["cpi.md:1", "cpi.md:2"]
    assert chunks[0]["uri"] == document_uri("cpi.md:1")
    assert chunks[0]["text"] == "中国 CPI 数据说明"

    found = index.document_chunk("cpi.md:1")
    assert found is not None
    assert found["title"] == "Doc cpi.md:1"

    assert index.document_chunk("missing") is None


def test_search_results_carry_documentation_uri() -> None:
    catalog = {"macro_china_cpi": _api("macro_china_cpi")}
    index = CatalogIndex(
        catalog,
        documents=[_chunk("cpi.md:1", ["macro_china_cpi"], text="CPI 文档说明")],
    )
    payload = index.search_payload("CPI")
    doc_refs = payload["results"][0]["documentation"]
    assert doc_refs
    assert doc_refs[0]["uri"] == document_uri("cpi.md:1")
    assert doc_refs[0]["source_url"] == "https://example.test/cpi.md:1"


def test_document_uri_escapes_spaces_and_reserved_characters() -> None:
    uri = document_uri("nested path/cpi#1.md")
    assert uri == f"{DOC_URI_PREFIX}nested%20path%2Fcpi%231.md"


def test_chunks_without_id_are_indexed_for_search_but_not_resources() -> None:
    catalog = {"macro_china_cpi": _api("macro_china_cpi")}
    chunk = _chunk("", ["macro_china_cpi"], text="无 id 的文档")
    chunk["id"] = ""  # explicit empty id
    index = CatalogIndex(catalog, documents=[chunk])
    # Searchable.
    assert "无 id 的文档".casefold() in index._documents["macro_china_cpi"]
    # Not exposed as a resource.
    assert index.document_chunks() == []
