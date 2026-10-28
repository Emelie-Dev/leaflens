import logging
import os

import requests

logger = logging.getLogger(__name__)


def identify_crop(image_bytes: bytes) -> dict:
    api_key = os.getenv("PLANTNET_API_KEY")
    if not api_key:
        logger.warning("Pl@ntNet request failed: RuntimeError")
        return {"ok": False, "reason": "unavailable"}

    project = os.getenv("PLANTNET_PROJECT", "all")
    try:
        response = requests.post(
            f"https://my-api.plantnet.org/v2/identify/{project}",
            params={"api-key": api_key},
            files={"images": ("leaf.jpg", image_bytes, "image/jpeg")},
            data={"organs": "leaf"},
            timeout=(5, 20),
        )
    except requests.exceptions.Timeout as exc:
        logger.warning("Pl@ntNet request failed: %s", type(exc).__name__)
        return {"ok": False, "reason": "unavailable"}
    except requests.exceptions.ConnectionError as exc:
        logger.warning("Pl@ntNet request failed: %s", type(exc).__name__)
        return {"ok": False, "reason": "unavailable"}
    except Exception as exc:
        logger.warning("Pl@ntNet request failed: %s", type(exc).__name__)
        return {"ok": False, "reason": "unavailable"}

    if response.status_code == 404:
        return {"ok": False, "reason": "not_a_crop"}
    if response.status_code != 200:
        logger.warning("Pl@ntNet request failed with status %s", response.status_code)
        return {"ok": False, "reason": "unavailable"}

    try:
        results = response.json().get("results") or []
        if not results:
            return {"ok": False, "reason": "not_a_crop"}
        result = results[0]
        score = float(result["score"])
        species = result["species"]
        scientific = species["scientificNameWithoutAuthor"]
        if not isinstance(scientific, str) or not scientific.strip():
            raise ValueError
        common_names = species.get("commonNames") or []
        crop = common_names[0] if common_names else scientific
        if not isinstance(crop, str) or not crop.strip():
            crop = scientific
        crop = crop.strip()
        crop = (crop[0].upper() + crop[1:])[:100]
    except Exception as exc:
        logger.warning("Pl@ntNet response failed: %s", type(exc).__name__)
        return {"ok": False, "reason": "unavailable"}

    return {
        "ok": True,
        "crop": crop,
        "scientific": scientific.strip(),
        "score": score,
    }
