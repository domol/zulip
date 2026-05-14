import logging
from collections.abc import Mapping
from typing import Any

from typing_extensions import override

from zerver.worker.base import QueueProcessingWorker, assign_queue

logger = logging.getLogger(__name__)


@assign_queue("message_moderation")
class MessageModerationWorker(QueueProcessingWorker):
    @override
    def consume(self, event: Mapping[str, Any]) -> None:
        from safechat_moderation.classifiers.registry import get_enabled_classifiers
        from safechat_moderation.models import FlaggedMessage

        content: str = event["content"]
        if not content.strip():
            return

        for classifier, threshold, flag_labels in get_enabled_classifiers():
            try:
                result = classifier.classify(content)
            except Exception:
                logger.exception(
                    "Classifier %s failed on message %s",
                    classifier.name,
                    event["message_id"],
                )
                continue

            if result.score >= threshold and result.label in flag_labels:
                FlaggedMessage.objects.create(
                    message_id=event["message_id"],
                    realm_id=event["realm_id"],
                    sender_id=event.get("sender_id"),
                    content_preview=content[:500],
                    classifier=result.classifier_name,
                    score=result.score,
                    label=result.label,
                    stream_id=event.get("stream_id"),
                    stream_name=event.get("stream_name", ""),
                    topic_name=event.get("topic_name", ""),
                    is_dm=event.get("is_dm", False),
                )
