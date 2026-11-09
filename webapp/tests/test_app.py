from io import BytesIO

import numpy as np
import pytest
from PIL import Image

import app as app_module


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(app_module.app.config, "TESTING", True)
    monkeypatch.setitem(app_module.app.config, "SECRET_KEY", "test-secret")
    return app_module.app.test_client()


def log_in(client):
    with client.session_transaction() as user_session:
        user_session["user_id"] = 1


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok"


def test_predict_requires_login(client):
    response = client.post("/api/predict")

    assert response.status_code == 401
    assert response.get_json() == {"error": "Please log in first."}


def test_predict_requires_an_image(client):
    log_in(client)

    response = client.post("/api/predict")

    assert response.status_code == 400
    assert response.get_json() == {"error": "Please choose an image."}


def test_predict_rejects_an_unreadable_image(client):
    log_in(client)

    response = client.post(
        "/api/predict",
        data={"file": (BytesIO(b"not an image"), "leaf.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "That file isn't a readable image."}


def test_model_info_reports_missing_model(client, monkeypatch):
    def missing_model():
        raise FileNotFoundError("model not uploaded")

    monkeypatch.setattr(app_module, "load_model", missing_model)

    response = client.get("/api/model")

    assert response.status_code == 200
    assert response.get_json() == {"ready": False, "error": "model not uploaded"}


def test_preprocess_returns_normalized_nchw_float32():
    image = Image.new("RGB", (4, 4), (255, 255, 255))

    result = app_module.preprocess(image)

    assert result.shape == (1, 3, 224, 224)
    assert result.dtype == np.float32
    np.testing.assert_allclose(
        result[0, :, 0, 0],
        (1 - app_module.MEAN) / app_module.STD,
        rtol=1e-6,
    )


def test_estimate_severity_for_healthy_and_mixed_leaves():
    healthy_leaf = Image.new("RGB", (256, 256), (0, 128, 0))
    mixed_leaf_pixels = np.empty((256, 256, 3), dtype=np.uint8)
    mixed_leaf_pixels[:, :128] = (0, 128, 0)
    mixed_leaf_pixels[:, 128:] = (255, 255, 0)
    mixed_leaf = Image.fromarray(mixed_leaf_pixels)

    assert app_module.estimate_severity(healthy_leaf) == 0.0
    assert app_module.estimate_severity(mixed_leaf) == 50.0


def test_estimate_severity_ignores_background():
    background = Image.new("RGB", (256, 256), (255, 255, 255))

    assert app_module.estimate_severity(background) == 0.0


def test_pretty_formats_known_and_unknown_labels():
    assert app_module.pretty("Apple___Apple_scab") == ("Apple", "Apple scab")
    assert app_module.pretty("Mystery_Unknown_disease") == (
        "Mystery",
        "Mystery Unknown disease",
    )
