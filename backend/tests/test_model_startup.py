"""Startup warms the model automatically, while unavailable weights keep enhancement usable."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.api import routes
from app.algorithms import face_detector
from test_api import photo


def test_startup_loads_model_without_manual_request(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "face_engine", SimpleNamespace(load=lambda: calls.append("loaded")))
    with TestClient(main.app) as client:
        assert calls == ["loaded"]
        assert client.get("/api/person").status_code == 200
    assert calls == ["loaded"]


def test_missing_startup_weights_keep_enhancement_available_and_face_errors_actionable(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(face_detector, "MODEL_ROOT", tmp_path)
    unavailable = face_detector.FaceEngine()
    monkeypatch.setattr(main, "face_engine", unavailable)
    monkeypatch.setattr(routes, "engine", unavailable)
    with TestClient(main.app) as client:
        assert not unavailable.status()["ready"]
        assert "人脸模型自动加载未完成" in caplog.text
        image = {"file": ("photo.png", photo(), "image/png")}
        assert client.post("/api/enhance/process", files=image).status_code == 200
        response = client.post("/api/face/detect", files=image)
        assert response.status_code == 503
        assert "scripts/download_models.py" in response.json()["message"]
        assert "点击加载" not in response.json()["message"]
