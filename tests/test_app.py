from fastapi.testclient import TestClient

from media_moderation_api import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"healthy", "degraded"}
    assert data["service"] == "x02_unified_media_moderation_v2"
    assert "model" in data


def test_info_endpoint():
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert data["service"].startswith("x02 Unified Media Moderation")
    assert "supported_formats" in data
    assert "endpoints" in data


def test_moderate_gif_rejects_non_gif_file():
    response = client.post(
        "/moderate-gif",
        files={"file": ("invalid.jpg", b"fake content", "image/jpeg")},
    )
    assert response.status_code == 415


def test_moderate_video_rejects_non_video_file():
    response = client.post(
        "/moderate-video",
        data={"frame_interval": "5"},
        files={"file": ("invalid.jpg", b"fake content", "image/jpeg")},
    )
    assert response.status_code == 415
