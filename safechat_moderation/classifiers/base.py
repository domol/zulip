from dataclasses import dataclass


@dataclass
class ClassificationResult:
    label: str
    score: float
    classifier_name: str


class BaseMessageClassifier:
    name: str

    def classify(self, text: str) -> ClassificationResult:
        raise NotImplementedError
