from pathlib import Path


def test_core_source_tree_has_no_external_ingestion_or_ai_adapters() -> None:
    root = Path(__file__).parents[2] / "src" / "andromeda_core"
    forbidden = (
        "from bs4",
        "from pypdf",
        "import playwright",
        "import openai",
        "import anthropic",
        "IngestionPipelineService",
        "StructuredJsonHttpAIAdapter",
        "SafeHttpFetcher",
        "BeautifulSoup",
        "PdfReader",
        "ingestion_pipeline_runs",
    )

    violations = [
        f"{path}:{needle}"
        for path in root.rglob("*.py")
        for needle in forbidden
        if needle in path.read_text(encoding="utf-8")
    ]
    assert violations == []
