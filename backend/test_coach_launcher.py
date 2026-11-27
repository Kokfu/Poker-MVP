from fastapi import FastAPI
from fastapi.testclient import TestClient

from coach.launcher import BuiltCoach


def test_launcher_serves_only_built_files_on_the_web_port(tmp_path):
    (tmp_path / "index.html").write_text("<main>Built Coach</main>", encoding="utf-8")
    (tmp_path / "service-worker.js").write_text("// built worker", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "bundle.js").write_text("// built bundle", encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "unregistered").write_text("outside API", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "OK"}

    app.mount("/", BuiltCoach(tmp_path, 5178))
    with TestClient(app, base_url="http://127.0.0.1:5178") as client:
        page = client.get("/")
        assert page.text == "<main>Built Coach</main>"
        assert page.headers["cache-control"] == "no-cache"
        assert client.get("/service-worker.js").headers["cache-control"] == "no-cache"
        assert client.get("/assets/bundle.js").text == "// built bundle"
        assert client.get("/src/App.tsx").status_code == 404
        assert client.get("/@vite/client").status_code == 404
        assert client.get("/api/unregistered").status_code == 404
        assert client.get("/api/health").json() == {"status": "OK"}
        assert client.get("http://127.0.0.1:8014/api/health").json() == {"status": "OK"}
        assert client.get("http://127.0.0.1:8014/").status_code == 404
