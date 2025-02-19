from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from django.core.management.base import BaseCommand
from django.db.models import Q, F, Count

from postman.models import Message

if TYPE_CHECKING:
    from collections.abc import Iterable

    _CHECK_T2 = tuple[str, Q]
    _CHECK_T4 = tuple[str, Q, dict[str, Any], Q]


class Command(BaseCommand):
    help = "Can be run as a cron job or directly to check-up data consistency in the database."

    # no more NoArgsCommand and handle_noargs with Dj >= 1.8
    def handle(self, *args: Any, **options: Any):
        verbose = int(cast(Any, options.get('verbosity')))  # discard unexpected None
        if verbose >= 1:
            self.stdout.write(datetime.now().strftime("%H:%M:%S ") + "Checking messages and conversations for inconsistencies...")
        checks: list['_CHECK_T2 | _CHECK_T4'] = [
            ("Sender and Recipient cannot be both undefined.", Q(sender__isnull=True, recipient__isnull=True)),
            ("Visitor's email is in excess.", Q(sender__isnull=False, recipient__isnull=False) & ~Q(email='')),
            ("Visitor's email is missing.", (Q(sender__isnull=True) | Q(recipient__isnull=True)) & Q(email='')),
            ("Reading date must be later than sending date.", Q(read_at__lt=F('sent_at'))),
            ("Deletion date by sender must be later than sending date.", Q(sender_deleted_at__lt=F('sent_at'))),
            ("Deletion date by recipient must be later than sending date.", Q(recipient_deleted_at__lt=F('sent_at'))),
            ("Response date must be later than sending date.", Q(replied_at__lt=F('sent_at'))),
            ("The message cannot be replied without having been read.", Q(replied_at__isnull=False, read_at__isnull=True)),
            ("Response date must be later than reading date.", Q(replied_at__lt=F('read_at'))),
            # because of the delay due to the moderation, no constraint between replied_at and recipient_deleted_at
            ("Response date cannot be set without at least one reply.",
                Q(replied_at__isnull=False), {'cnt': Count('next_messages')}, Q(cnt=0)),
                # cnt should filter to allow only accepted replies, but do not know how to specify it
            ("The message cannot be replied without being in a conversation.",
                Q(replied_at__isnull=False, thread__isnull=True)),
            ("The message cannot be a reply without being in a conversation.",
                Q(parent__isnull=False, thread__isnull=True)),
            ("The reply and its parent are not in a conversation in common.",
                Q(parent__isnull=False, thread__isnull=False) & (Q(parent__thread__isnull=True) | ~Q(parent__thread=F('thread')))),
        ]
        count = 0
        for c in checks:
            msgs = Message.objects.filter(c[1])
            if len(c) >= 4:
                c4 = cast('_CHECK_T4', c)
                # Meta.ordering is no more used with GROUP BY clause in Django 3.1, set the ordering explicitly here.
                msgs = msgs.annotate(**c4[2]).filter(c4[3]).order_by('-sent_at', '-id')
            if msgs:
                count += len(msgs)
                self.report_errors(c[0], msgs)
        if verbose >= 1:
            self.stdout.write(datetime.now().strftime("%H:%M:%S ") +
                ("Number of inconsistencies found: {0}. See details on the error stream.".format(count) if count
                else "All is correct."))

    def report_errors(self, reason: str, msgs: 'Iterable[Message]'):
        self.stderr.write(reason)
        self.stderr.write("  {0:6} {1:5} {2:5} {3:10} {4:6} {5:6} {6:16} {7:16} {8:16}".format(
            "Id","From","To","Email","Parent","Thread","Sent","Read","Replied"))
        for msg in msgs:
            self.stderr.write(
                "  {0.pk:6} {0.sender_id!s:5} {0.recipient_id!s:5} {0.email:10.10} {0.parent_id!s:6} {0.thread_id!s:6}"
                " {0.sent_at!s:16.16} {0.read_at!s:16.16} {0.replied_at!s:16.16}".format(msg))
