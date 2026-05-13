from typing import Any

from .base import BaseMessageClassifier, ClassificationResult


class HateSpeechClassifier(BaseMessageClassifier):
    name = "hate_speech_xlm"
    model_name = "cardiffnlp/twitter-xlm-roberta-base-hate"

    def __init__(self) -> None:
        self._pipeline: Any = None

    def classify(self, text: str) -> ClassificationResult:
        if self._pipeline is None:
            from transformers import pipeline

            self._pipeline = pipeline("text-classification", model=self.model_name)
        result = self._pipeline(text, truncation=True, max_length=512)[0]
        return ClassificationResult(
            label=result["label"],
            score=float(result["score"]),
            classifier_name=self.name,
        )
