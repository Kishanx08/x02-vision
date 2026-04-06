"""Text moderation using a DistilBERT-compatible classifier with keyword fallback."""

import re
from typing import Dict, List, Optional

try:
    from transformers import pipeline
except ImportError:  # pragma: no cover - optional dependency
    pipeline = None


class TextModerationService:
    """Moderate OCR text with a DistilBERT zero-shot classifier."""

    CANDIDATE_LABELS = [
        "safe text",
        "explicit sexual content",
        "abusive or hateful content",
        "violent threat",
    ]
    KEYWORD_RULES = {
        "explicit sexual content": [
            "nsfw", "xxx", "porn", "nude", "nudes", "sex", "onlyfans",
            "blowjob", "anal", "cum", "dick", "pussy"
        ],
        "abusive or hateful content": [
            "kill yourself", "kys", "die bitch", "whore", "slut", "faggot",
            "nigger", "retard", "cunt", "bitch", "bastard"
        ],
        "violent threat": [
            "i will kill", "i'll kill", "shoot you", "stab you", "murder you"
        ],
    }

    def __init__(
        self,
        model_name: str = "typeform/distilbert-base-uncased-mnli",
        threshold: float = 0.6,
    ):
        self.model_name = model_name
        self.threshold = threshold
        self._classifier = None

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _get_classifier(self):
        if pipeline is None:
            return None
        if self._classifier is None:
            self._classifier = pipeline(
                "zero-shot-classification",
                model=self.model_name,
            )
        return self._classifier

    def _keyword_fallback(self, text: str) -> Dict:
        normalized = self._normalize(text)
        hits = []

        for label, keywords in self.KEYWORD_RULES.items():
            matched = [keyword for keyword in keywords if keyword in normalized]
            if matched:
                hits.append({
                    "label": label,
                    "score": 1.0,
                    "matches": matched,
                })

        if not hits:
            return {
                "label": "safe text",
                "score": 1.0,
                "labels": ["safe text"],
                "scores": [1.0],
                "method": "keyword_fallback",
            }

        top = hits[0]
        return {
            "label": top["label"],
            "score": top["score"],
            "labels": [hit["label"] for hit in hits],
            "scores": [hit["score"] for hit in hits],
            "method": "keyword_fallback",
            "matches": top["matches"],
        }

    def moderate_text(self, text: str) -> Dict:
        normalized = self._normalize(text)
        if not normalized:
            return {
                "label": "safe text",
                "score": 1.0,
                "labels": ["safe text"],
                "scores": [1.0],
                "method": "empty_text",
            }

        classifier = self._get_classifier()
        if classifier is None:
            return self._keyword_fallback(normalized)

        result = classifier(normalized, self.CANDIDATE_LABELS, multi_label=True)
        labels = result.get("labels", [])
        scores = result.get("scores", [])
        top_label = labels[0] if labels else "safe text"
        top_score = float(scores[0]) if scores else 1.0

        return {
            "label": top_label,
            "score": top_score,
            "labels": labels,
            "scores": [float(score) for score in scores],
            "method": "distilbert_zero_shot",
        }

    def moderate_ocr_result(self, ocr_result: Dict) -> Dict:
        if not ocr_result.get("enabled", False):
            return {"enabled": False, "available": False, "reason": "OCR disabled"}
        if not ocr_result.get("available", False):
            return {
                "enabled": True,
                "available": False,
                "reason": ocr_result.get("reason", "OCR unavailable"),
            }

        entries = []
        matched_categories = []

        for item in ocr_result.get("extracted_text", []):
            text = item.get("text", "")
            moderation = self.moderate_text(text)
            flagged = (
                moderation["label"] != "safe text"
                and moderation["score"] >= self.threshold
            )
            if flagged:
                matched_categories.append(moderation["label"])

            entries.append({
                "frame_idx": item.get("frame_idx"),
                "text": text,
                "moderation": moderation,
                "flagged": flagged,
            })

        unique_categories = sorted(set(matched_categories))
        return {
            "enabled": True,
            "available": True,
            "model": self.model_name if pipeline is not None else "keyword_fallback",
            "matched": bool(unique_categories),
            "categories": unique_categories,
            "entries": entries,
            "recommendation": "soft_flag" if unique_categories else "allow",
        }
