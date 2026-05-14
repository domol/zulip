import contextlib
import logging
import os
import re
import smtplib
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import timedelta
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import Parser
from email.policy import default
from email.utils import formataddr, parseaddr
from email.utils import formatdate as email_formatdate
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import css_inline
import orjson
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import sanitize_address
from django.core.management import CommandError
from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.db.models.functions import Lower
from django.http import HttpRequest
from django.template import loader
from django.utils.timezone import now as timezone_now
from django.utils.translation import gettext as _
from django.utils.translation import override as override_language

from confirmation.models import generate_key
from zerver.lib.logging_util import log_to_file
from zerver.lib.queue import queue_event_on_commit
from zerver.models import Realm, RealmAuditLog, ScheduledEmail, UserProfile
from zerver.models.realm_audit_logs import AuditLogEventType
from zerver.models.scheduled_jobs import EMAIL_TYPES
from zerver.models.users import get_user_profile_by_id
from zproject.email_backends import smtp_connection_backoff

if settings.ZILENCER_ENABLED:
    from zilencer.models import RemoteZulipServer

## Logging setup ##

logger = logging.getLogger("zulip.send_email")
log_to_file(logger, settings.EMAIL_LOG_PATH)


def get_inliner_instance() -> css_inline.CSSInliner:
    return css_inline.CSSInliner()


class FromAddress:
    SUPPORT = parseaddr(settings.ZULIP_ADMINISTRATOR)[1]
    NOREPLY = parseaddr(settings.NOREPLY_EMAIL_ADDRESS)[1]

    support_placeholder = "SUPPORT"
    no_reply_placeholder = "NO_REPLY"
    tokenized_no_reply_placeholder = "TOKENIZED_NO_REPLY"

    # Generates an unpredictable noreply address.
    @staticmethod
    def tokenized_no_reply_address() -> str:
        if settings.ADD_TOKENS_TO_NOREPLY_ADDRESS:
            return parseaddr(settings.TOKENIZED_NOREPLY_EMAIL_ADDRESS)[1].format(
                token=generate_key()
            )
        return FromAddress.NOREPLY

    @staticmethod
    def security_email_from_name(
        language: str | None = None, user_profile: UserProfile | None = None
    ) -> str:
        if language is None:
            assert user_profile is not None
            language = user_profile.default_language

        with override_language(language):
            return _("{service_name} account security").format(
                service_name=settings.INSTALLATION_NAME
            )


def build_email(
    template_prefix: str,
    to_user_ids: list[int] | None = None,
    to_emails: list[str] | None = None,
    from_name: str | None = None,
    from_address: str | None = None,
    reply_to_email: str | None = None,
    language: str | None = None,
    date: str | None = None,
    context: Mapping[str, Any] = {},
    realm: Realm | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> EmailMultiAlternatives:
    # Callers should pass exactly one of to_user_id and to_email.
    assert (to_user_ids is None) ^ (to_emails is None)
    if to_user_ids is not None:
        to_users = [get_user_profile_by_id(to_user_id) for to_user_id in to_user_ids]
        if realm is None:
            assert len({to_user.realm_id for to_user in to_users}) == 1
            realm = to_users[0].realm
        to_emails = []
        for to_user in to_users:
            stringified = str(
                Address(display_name=to_user.full_name, addr_spec=to_user.delivery_email)
            )
            # Check ASCII encoding length.  Amazon SES rejects emails
            # with From or To values longer than 320 characters (which
            # appears to be a misinterpretation of the RFC); in that
            # case we drop the name part from the address, under the
            # theory that it's better to send the email with a
            # simplified field than not at all.
            if len(sanitize_address(stringified, "utf-8")) > 320:
                stringified = str(Address(addr_spec=to_user.delivery_email))
            to_emails.append(stringified)

    # Attempt to suppress all auto-replies.  This header originally
    # came out of Microsoft Outlook and friends, but seems reasonably
    # commonly-recognized.
    extra_headers = {"X-Auto-Response-Suppress": "All"}

    if date is None:
        # Messages enqueued via the `email_senders` queue provide a
        # Date header of when they were enqueued; Django would also
        # add a default-now header if we left this off, but doing so
        # ourselves here explicitly makes it slightly more consistent.
        date = email_formatdate()
    extra_headers["Date"] = date

    if realm is not None:
        # formaddr is meant for formatting (display_name, email_address) pair for headers like "To",
        # but we can use its utility for formatting the List-Id header, as it follows the same format,
        # except having just a domain instead of an email address.
        extra_headers["List-Id"] = formataddr((realm.name, realm.host))

    if in_reply_to is not None:
        extra_headers["In-Reply-To"] = in_reply_to

    if references is not None:
        extra_headers["References"] = references

    assert settings.STATIC_URL is not None
    context = {
        **context,
        "support_email": FromAddress.SUPPORT,
        # Emails use unhashed image URLs so that those continue to
        # work over time, even if the prod-static directory is cleaned
        # out; as such, they just use a STATIC_URL prefix.
        "email_images_base_url": settings.STATIC_URL + "images/emails",
        "physical_address": settings.PHYSICAL_ADDRESS,
    }

    def get_inlined_template(template: str) -> str:
        inliner = get_inliner_instance()
        return inliner.inline(template)

    def render_templates() -> tuple[str, str, str]:
        email_subject = (
            loader.render_to_string(
                template_prefix + ".subject.txt", context=context, using="Jinja2_plaintext"
            )
            .strip()
            .replace("\n", "")
        )
        message = loader.render_to_string(
            template_prefix + ".txt", context=context, using="Jinja2_plaintext"
        )

        html_message = loader.render_to_string(template_prefix + ".html", context)
        return (get_inlined_template(html_message), message, email_subject)

    # The i18n story for emails is a bit complicated.  For emails
    # going to a single user, we want to use the language that user
    # has configured for their Zulip account.  For emails going to
    # multiple users or to email addresses without a known Zulip
    # account (E.g. invitations), we want to use the default language
    # configured for the Zulip organization.
    #
    # See our i18n documentation for some high-level details:
    # https://zulip.readthedocs.io/en/latest/translating/internationalization.html

    if not language and to_user_ids is not None:
        language = to_users[0].default_language
    if language:
        with override_language(language):
            # Make sure that we render the email using the target's native language
            (html_message, message, email_subject) = render_templates()
    else:
        (html_message, message, email_subject) = render_templates()
        logger.warning("Missing language for email template '%s'", template_prefix)

    if from_name is None:
        from_name = "SafeChat"
    if from_address is None:
        from_address = FromAddress.NOREPLY
    if from_address == FromAddress.tokenized_no_reply_placeholder:
        from_address = FromAddress.tokenized_no_reply_address()
    if from_address == FromAddress.no_reply_placeholder:
        from_address = FromAddress.NOREPLY
    if from_address == FromAddress.support_placeholder:
        from_address = FromAddress.SUPPORT

    # Set the "From" that is displayed separately from the envelope-from.
    extra_headers["From"] = str(Address(display_name=from_name, addr_spec=from_address))
    # As above, with the "To" line, we drop the name part if it would
    # result in an address which is longer than 320 bytes.
    if len(sanitize_address(extra_headers["From"], "utf-8")) > 320:
        extra_headers["From"] = str(Address(addr_spec=from_address))

    # If we have an unsubscribe link for this email, configure it for
    # "Unsubscribe" buttons in email clients via the List-Unsubscribe header.
    #
    # Note that Microsoft ignores URLs in List-Unsubscribe headers, as
    # they only support the alternative `mailto:` format, which we
    # have not implemented.
    if "unsubscribe_link" in context:
        extra_headers["List-Unsubscribe"] = f"<{context['unsubscribe_link']}>"
        if not context.get("remote_server_email", False):
            extra_headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    reply_to = None
    if reply_to_email is not None:
        reply_to = [reply_to_email]
    # Remove the from_name in the reply-to for noreply emails, so that users
    # see "noreply@..." rather than "SafeChat" or whatever the from_name is
    # when they reply in their email client.
    elif from_address == FromAddress.NOREPLY:
        reply_to = [FromAddress.NOREPLY]

    envelope_from = FromAddress.NOREPLY
    mail = EmailMultiAlternatives(
        email_subject, message, envelope_from, to_emails, reply_to=reply_to, headers=extra_headers
    )
    if html_message is not None:
        mail.attach_alternative(html_message, "text/html")
    return mail


class EmailNotDeliveredError(Exception):
    pass


class DoubledEmailArgumentError(CommandError):
    def __init__(self, argument_name: str) -> None:
        msg = (
            f"Argument '{argument_name}' is ambiguously present in both options and email template."
        )
        super().__init__(msg)


class NoEmailArgumentError(CommandError):
    def __init__(self, argument_name: str) -> None:
        msg = f"Argument '{argument_name}' is required in either options or email template."
        super().__init__(msg)


@smtp_connection_backoff
def _send_messages(connection: BaseEmailBackend, messages: list[EmailMultiAlternatives]) -> int:
    return connection.send_messages(messages)


# When changing the arguments to this function, you may need to write a
# migration to change or remove any emails in ScheduledEmail.
def send_immediate_email(
    template_prefix: str,
    to_user_ids: list[int] | None = None,
    to_emails: list[str] | None = None,
    from_name: str | None = None,
    from_address: str | None = None,
    reply_to_email: str | None = None,
    language: str | None = None,
    date: str | None = None,
    context: Mapping[str, Any] = {},
    realm: Realm | None = None,
    connection: BaseEmailBackend | None = None,
    dry_run: bool = False,
    request: HttpRequest | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    remove_suppressed_destination: bool = False,
) -> None:
    mail = build_email(
        template_prefix,
        to_user_ids=to_user_ids,
        to_emails=to_emails,
        from_name=from_name,
        from_address=from_address,
        reply_to_email=reply_to_email,
        language=language,
        date=date,
        context=context,
        realm=realm,
        in_reply_to=in_reply_to,
        references=references,
    )
    template = template_prefix.rsplit("/", 1)[-1]

    log_email_config_errors()

    if dry_run:
        print(mail.message().get_payload()[0])
        return

    owns_connection = connection is None
    if owns_connection:
        connection = get_connection()
    assert connection is not None

    cause = ""
    if request is not None:
        cause = f" (triggered from {request.META['REMOTE_ADDR']})"

    if realm is not None:
        logging_recipient = f"{mail.to} in {realm.string_id}"
    else:
        logging_recipient = f"{mail.to}"

    if remove_suppressed_destination:
        maybe_remove_from_suppression_list(mail.to)
    logger.info("Sending %s email to %s%s", template, logging_recipient, cause)

    try:
        # When we created the connection (no caller-provided one),
        # retry with backoff on transient connection failures.
        # Caller-provided connections (e.g. PersistentSMTPEmailBackend)
        # manage their own lifecycle via ensure_connected().
        if owns_connection:
            result = _send_messages(connection, [mail])
        else:
            result = connection.send_messages([mail])
        if result == 0:
            logger.error("Unknown error sending %s email to %s", template, mail.to)
            connection.close()
            raise EmailNotDeliveredError
    except smtplib.SMTPResponseException as e:
        logger.exception(
            "Error sending %s email to %s with error code %s: %s",
            template,
            mail.to,
            e.smtp_code,
            e.smtp_error,
            stack_info=True,
        )
        connection.close()
        raise EmailNotDeliveredError from e
    except (smtplib.SMTPException, OSError) as e:
        logger.exception("Error sending %s email to %s: %s", template, mail.to, e, stack_info=True)
        connection.close()
        raise EmailNotDeliveredError from e


def send_email(
    template_prefix: str,
    to_user_ids: list[int] | None = None,
    to_emails: list[str] | None = None,
    from_name: str | None = None,
    from_address: str | None = None,
    reply_to_email: str | None = None,
    language: str | None = None,
    date: str | None = None,
    context: Mapping[str, Any] = {},
    realm: Realm | None = None,
    connection: BaseEmailBackend | None = None,
    dry_run: bool = False,
    remove_suppressed_destination: bool = False,
    request: HttpRequest | None = None,
) -> None:
    if settings.EMAIL_ALWAYS_ENQUEUED and not dry_run:
        queue_event_on_commit(
            "email_senders",
            dict(
                template_prefix=template_prefix,
                to_user_ids=to_user_ids,
                to_emails=to_emails,
                from_name=from_name,
                from_address=from_address,
                reply_to_email=reply_to_email,
                language=language,
                date=date,
                context=context,
                realm_id=realm.id if realm is not None else None,
                remove_suppressed_destination=remove_suppressed_destination,
            ),
        )
    else:
        if settings.TEST_SUITE:
            # In tests, verify that the context object is
            # JSON-serializable, as may happen in production using
            # EMAIL_ALWAYS_ENQUEUED, above.
            context = orjson.loads(orjson.dumps(context))
        send_immediate_email(
            template_prefix,
            to_user_ids,
            to_emails,
            from_name,
            from_address,
            reply_to_email,
            language,
            date,
            context,
            realm,
            connection,
            dry_run,
            request,
            remove_suppressed_destination=remove_suppressed_destination,
        )


def send_future_email(
    template_prefix: str,
    realm: Realm,
    to_user_ids: list[int] | None = None,
    to_emails: list[str] | None = None,
    from_name: str | None = None,
    from_address: str | None = None,
    language: str | None = None,
    context: Mapping[str, Any] = {},
    delay: timedelta = timedelta(0),
) -> None:
    template_name = template_prefix.rsplit("/", 1)[-1]
    email_fields = {
        "template_prefix": template_prefix,
        "from_name": from_name,
        "from_address": from_address,
        "language": language,
        "context": context,
    }

    if settings.DEVELOPMENT_LOG_EMAILS:
        send_immediate_email(
            template_prefix,
            to_user_ids=to_user_ids,
            to_e