from __future__ import annotations

import asyncio
from pathlib import Path

from scripts.experiments.llama_cloud_smoke import run_live_smoke


class FakeParsing:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.get_calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "job": {"id": "pjb_smoke", "status": "COMPLETED"},
            "markdown": [{"page": 1, "markdown": "# Politica SST"}],
            "job_metadata": {"credits": 3},
        }

    async def get(self, job_id: str, **kwargs):
        self.get_calls.append({"job_id": job_id, **kwargs})
        return {
            "job": {"id": job_id, "status": "COMPLETED"},
            "metadata": [{"page": 1, "source": "synthetic"}],
        }


class FakeClassify:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "clf_smoke",
            "status": "COMPLETED",
            "result": {"type": "politica", "confidence": 0.91, "reasoning": "synthetic"},
        }


class FakeExtract:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": "ext_smoke",
            "status": "COMPLETED",
            "extract_result": {"document_title": "Politica SST", "document_code": "SST-TEST"},
        }


class FakeClient:
    def __init__(self) -> None:
        self.parsing = FakeParsing()
        self.classify = FakeClassify()
        self.extract = FakeExtract()


def test_live_smoke_reuses_parse_job_for_classify_and_extract(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.md"
    source.write_text("# Politica SST\n\nCodigo: SST-TEST", encoding="utf-8")
    output = tmp_path / "smoke.json"
    client = FakeClient()

    result = asyncio.run(
        run_live_smoke(
            client=client,
            source=source,
            output=output,
            document_id="synthetic-smoke",
        )
    )

    assert result["status"] == "completed"
    assert result["provider_job_ids"] == ["pjb_smoke", "clf_smoke", "ext_smoke"]
    assert client.parsing.calls[0]["tier"] == "cost_effective"
    assert client.parsing.calls[0]["expand"] == ["markdown", "items", "metadata", "job_metadata"]
    assert client.parsing.get_calls[0] == {
        "job_id": "pjb_smoke",
        "expand": ["metadata", "job_metadata"],
    }
    assert client.classify.calls[0]["file_input"] == "pjb_smoke"
    assert client.classify.calls[0]["configuration"]["mode"] == "FAST"
    assert client.extract.calls[0]["file_input"] == "pjb_smoke"
    assert client.extract.calls[0]["configuration"]["tier"] == "cost_effective"
    assert client.extract.calls[0]["configuration"]["parse_tier"] == "fast"
    serialized = output.read_text(encoding="utf-8").lower()
    assert "politica sst" not in serialized
    assert "codigo: sst-test" not in serialized
