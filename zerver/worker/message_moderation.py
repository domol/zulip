# Bridge module: Zulip discovers workers as zerver.worker.<queue_name>,
# so this file registers the safechat_moderation worker under that path.
from safechat_moderation.worker import MessageModerationWorker

__all__ = ["MessageModerationWorker"]
