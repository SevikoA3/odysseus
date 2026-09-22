from types import SimpleNamespace

from routes.chat_helpers import _project_file_fallbacks
from src.chat_processor import ChatProcessor, PROJECT_FILE_CONTEXT_POLICY
from src.rag_vector import VectorRAG
from tests.helpers.embedding_lanes import FakeChroma, FakeEmbedder, patch_chroma


def _rag(monkeypatch):
    fake = FakeChroma()
    patch_chroma(monkeypatch, fake)
    import src.embedding_lanes as lanes

    monkeypatch.setattr(lanes, "_build_custom_client", lambda: None)
    monkeypatch.setattr(
        lanes,
        "_build_fastembed_client",
        lambda: FakeEmbedder(384, "mini", "local://fastembed"),
    )
    return VectorRAG(), fake


def _project_metadata(owner, project_id, upload_id):
    return {
        "source": f"/uploads/{upload_id}.txt",
        "filename": f"{upload_id}.txt",
        "owner": owner,
        "scope": "project",
        "project_id": project_id,
        "upload_id": upload_id,
    }


def test_project_rag_isolates_vector_and_keyword_search(monkeypatch):
    rag, fake = _rag(monkeypatch)
    text = "shared project retrieval token"
    assert rag.add_document(text, _project_metadata("alice", "project-a", "upload-a"))
    assert rag.add_document(text, _project_metadata("alice", "project-b", "upload-b"))
    assert rag.add_document(text, _project_metadata("bob", "project-a", "upload-a"))
    assert rag.add_document(text, {"owner": "alice", "filename": "personal.txt"})

    collection = fake.collections["odysseus_rag_fastembed"]
    assert collection.count() == 4
    assert [row["metadata"]["upload_id"] for row in rag.search(
        "shared retrieval token",
        owner="alice",
        project_id="project-a",
        upload_ids={"upload-a"},
    )] == ["upload-a"]
    assert [row["metadata"]["upload_id"] for row in rag.search(
        "shared retrieval token",
        owner="alice",
        project_id="project-b",
        upload_ids={"upload-b"},
    )] == ["upload-b"]
    assert [row["metadata"]["filename"] for row in rag.search(
        "shared retrieval token", owner="alice"
    )] == ["personal.txt"]

    collection.query = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
    fallback = rag.search(
        "shared retrieval token",
        owner="alice",
        project_id="project-a",
        upload_ids={"upload-a"},
    )
    assert [row["metadata"]["upload_id"] for row in fallback] == ["upload-a"]
    assert fallback[0]["search_type"] == "keyword_fallback"


def test_project_rag_deletion_is_scoped_to_file_and_project(monkeypatch):
    rag, _fake = _rag(monkeypatch)
    assert rag.add_document("same text", _project_metadata("alice", "project-a", "upload-a"))
    assert rag.add_document("same text", _project_metadata("alice", "project-a", "upload-b"))
    assert rag.add_document("same text", _project_metadata("alice", "project-b", "upload-a"))

    removed = rag.delete_project_chunks("alice", "project-a", "upload-a")

    assert removed == {"success": True, "removed_count": 1}
    assert rag.search("same text", owner="alice", project_id="project-a", upload_ids={"upload-a"}) == []
    assert [row["metadata"]["upload_id"] for row in rag.search(
        "same text", owner="alice", project_id="project-a", upload_ids={"upload-b"}
    )] == ["upload-b"]
    assert rag.delete_project_chunks("alice", "project-a") == {"success": True, "removed_count": 1}
    assert rag.search("same text", owner="alice", project_id="project-a", upload_ids={"upload-b"}) == []
    assert [row["metadata"]["project_id"] for row in rag.search(
        "same text", owner="alice", project_id="project-b", upload_ids={"upload-a"}
    )] == ["project-b"]


def test_project_context_keeps_retrieved_files_untrusted():
    calls = []

    class Rag:
        def search(self, *args, **kwargs):
            calls.append((args, kwargs))
            return [{
                "document": "project file text",
                "similarity": 1.0,
                "metadata": _project_metadata("alice", "project-a", "upload-a"),
            }]

    processor = ChatProcessor(
        memory_manager=SimpleNamespace(),
        personal_docs_manager=SimpleNamespace(rag_manager=Rag()),
    )
    preface, sources, _web_sources = processor.build_context_preface(
        message="find project text",
        session=SimpleNamespace(),
        use_memory=False,
        project_id="project-a",
        project_owner="alice",
        project_upload_ids={"upload-a"},
    )

    assert calls[0][1] == {
        "k": 5,
        "owner": "alice",
        "project_id": "project-a",
        "upload_ids": {"upload-a"},
    }
    assert sources == [{
        "filename": "upload-a.txt",
        "snippet": "project file text",
        "similarity": 1.0,
        "project_id": "project-a",
        "upload_id": "upload-a",
    }]
    assert {"role": "system", "content": PROJECT_FILE_CONTEXT_POLICY} in preface
    file_message = next(message for message in preface if message.get("metadata", {}).get("source") == "retrieved documents")
    assert file_message["role"] == "user"
    assert file_message["metadata"]["trusted"] is False

    fallback_preface, fallback_sources, _web_sources = ChatProcessor(
        memory_manager=SimpleNamespace(),
        personal_docs_manager=SimpleNamespace(rag_manager=None),
    ).build_context_preface(
        message="find project text",
        session=SimpleNamespace(),
        use_memory=False,
        project_id="project-a",
        project_file_fallbacks=[{
            "document": "fallback project file text",
            "metadata": {"filename": "fallback.txt", "upload_id": "upload-a"},
        }],
    )
    fallback_message = next(message for message in fallback_preface if message.get("metadata", {}).get("source") == "project files")
    assert fallback_sources[0]["filename"] == "fallback.txt"
    assert fallback_message["role"] == "user"
    assert fallback_message["metadata"]["trusted"] is False


def test_project_context_uses_fallback_after_rag_miss_without_requerying():
    class Rag:
        def search(self, *args, **kwargs):
            raise AssertionError("precomputed project RAG result should be reused")

    preface, sources, _web_sources = ChatProcessor(
        memory_manager=SimpleNamespace(),
        personal_docs_manager=SimpleNamespace(rag_manager=Rag()),
    ).build_context_preface(
        message="scene 6 shot 11",
        session=SimpleNamespace(),
        use_memory=False,
        project_id="project-a",
        project_owner="alice",
        project_upload_ids={"upload-a"},
        project_rag_results=[],
        project_file_fallbacks=[{
            "document": "Scene 6 Shot 11 Start Frame: sunrise over forest.",
            "metadata": {"filename": "treatment.md", "upload_id": "upload-a"},
        }],
    )

    assert {"role": "system", "content": PROJECT_FILE_CONTEXT_POLICY} in preface
    assert sources[0]["filename"] == "treatment.md"
    assert any(message.get("metadata", {}).get("source") == "project files" for message in preface)


def test_project_file_fallback_is_capped_and_skips_corrupt_uploads(tmp_path):
    path = tmp_path / "project.txt"
    path.write_text("project fallback text. " * 600, encoding="utf-8")

    class Uploads:
        def resolve_upload(self, upload_id, **_kwargs):
            if upload_id == "bad":
                raise OSError("corrupt upload")
            return {"path": str(path)}

    chunks = _project_file_fallbacks(
        [
            {"upload_id": "bad", "filename": "bad.txt"},
            {"upload_id": "good", "filename": "good.txt"},
        ],
        Uploads(),
        "alice",
    )

    assert len(chunks) == 5
    assert all(chunk["metadata"]["filename"] == "good.txt" for chunk in chunks)


def test_project_file_fallback_prefers_matching_storyboard_chunk(tmp_path):
    master = tmp_path / "master.md"
    scenario = tmp_path / "scenario.md"
    treatment = tmp_path / "treatment.md"
    master.write_text(
        "Prompt scene guidance for episode 6. Every shot needs a start frame. " * 800,
        encoding="utf-8",
    )
    scenario.write_text("Character dialogue. " * 800, encoding="utf-8")
    treatment.write_text(
        "## 4. Scene 6 :\n"
        + ("Previous shot description. " * 80)
        + "\n- **Shot 11 :** CU. Raya says she studied toxicology. Camera statis.\n",
        encoding="utf-8",
    )

    class Uploads:
        def resolve_upload(self, upload_id, **_kwargs):
            return {"path": {"master": master, "scenario": scenario, "treatment": treatment}[upload_id]}

    chunks = _project_file_fallbacks(
        [
            {"upload_id": "master", "filename": "master.md"},
            {"upload_id": "scenario", "filename": "scenario.md"},
            {"upload_id": "treatment", "filename": "treatment.md"},
        ],
        Uploads(),
        "alice",
        "create prompt scene 6 shot 11 start frame",
    )

    assert chunks[0]["metadata"]["filename"] == "treatment.md"
    assert "[Section: 4. Scene 6 :]" in chunks[0]["document"]
    assert "Shot 11" in chunks[0]["document"]
