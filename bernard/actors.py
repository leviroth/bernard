"""Classes that carry out specific actions on posts and comments."""
import base64
import json
import logging
import time
import urllib.parse
import zlib
from collections import namedtuple
from xml.sax.saxutils import unescape

import praw
import prawcore

from . import helpers


def update(self, transformation, reason=None):
    """Safely update a page based on its current content.

    :param transformation: A function taking the previous content as its
        sole parameter and returning the new content.
    :param reason: (Optional) The reason for the revision.

    """
    current_revision = next(self.revisions(limit=1))
    revision_id = current_revision['id']
    content = current_revision['page'].content_md
    new_content = transformation(content)
    while True:
        try:
            self.edit(new_content, reason=reason, previous=revision_id)
            return
        except prawcore.exceptions.Conflict as conflict:
            response_body = json.loads(conflict.response.content.decode())
            new_content = transformation(response_body['newcontent'])
            revision_id = response_body['newrevision']


praw.models.WikiPage.update = update


class Actor:
    """A class for managing rules.

    Responsible for matching input with commands, performing the requested
    actions, and logging to database.

    """

    def __init__(self, trigger, targets, remove, subactors, action_name,
                 action_details, database, subreddit):
        """Initialize the Actor class."""
        self.trigger = trigger
        self.targets = targets
        self.remove = remove
        self.subactors = subactors
        self.action_name = action_name
        self.action_details = action_details
        self.database = database
        self.cursor = database.cursor()
        self.subreddit = subreddit

    def match(self, command, thing):
        """Return true if command matches and thing is the right type."""
        return self.trigger.match(command) \
            and any(isinstance(thing, target) for target in self.targets)

    def parse(self, command, mod, post):
        """Execute requested actions if report matches command."""
        if self.match(command, post):
            # Only act once on a given thing
            target_type, target_id = helpers.deserialize_thing_id(
                post.fullname)
            self.cursor.execute('SELECT 1 FROM actions '
                                'WHERE target_type = ? AND target_id = ?',
                                (target_type, target_id))
            if self.cursor.fetchone() is not None:
                return

            action_id = self.log_action(post, mod)

            for subactor in self.subactors:
                subactor.action(post, mod, action_id=action_id)

            if self.remove:
                self.remove_thing(post, action_id=action_id)
            else:
                post.mod.approve()

            self.database.commit()

    def remove_thing(self, thing, action_id):
        """Perform and log removal. Lock if thing is a submission."""
        try:
            thing.mod.remove()
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to remove %s: %s", thing, exception)

        if isinstance(thing, praw.models.Submission):
            try:
                thing.mod.lock()
            except prawcore.exceptions.RequestException as exception:
                logging.error("Failed to lock %s: %s", thing, exception)

        self.cursor.execute('INSERT INTO removals (action_id) VALUES(?)',
                            (action_id, ))

    def log_action(self, target, moderator):
        """Log action in database and console. Return database row id."""
        target_type, target_id = helpers.deserialize_thing_id(target.fullname)
        action_summary = self.action_name
        action_details = self.action_details

        # If author deletes their account, target.author shows up as None
        if target.author is None:
            author_name = "[deleted]"
        else:
            author_name = target.author.name

        # Get (or create) database entries for author and moderator
        self.cursor.execute('INSERT OR IGNORE INTO users (username) '
                            'VALUES(?)', (author_name, ))
        self.cursor.execute('SELECT id FROM users WHERE username = ?',
                            (author_name, ))
        author_id = self.cursor.fetchone()[0]
        self.cursor.execute('INSERT OR IGNORE INTO users (username) '
                            'VALUES(?)', (moderator, ))
        self.cursor.execute('SELECT id FROM users WHERE username = ?',
                            (moderator, ))
        moderator_id = self.cursor.fetchone()[0]

        _, subreddit = helpers.deserialize_thing_id(self.subreddit.fullname)

        self.cursor.execute(
            'INSERT INTO actions (target_type, target_id, action_summary, '
            'action_details, author, moderator, subreddit) '
            'VALUES(?,?,?,?,?,?,?)', (target_type, target_id, action_summary,
                                      action_details, author_id, moderator_id,
                                      subreddit))

        print(moderator, action_summary, action_details, target,
              self.subreddit)

        return self.cursor.lastrowid


class Ledger:  # pylint: disable=too-few-public-methods
    """Abstract class for managing buffered updates."""

    def __init__(self, subreddit):
        """Initialize the Ledger class."""
        self.subreddit = subreddit

    def after(self):
        """Perform actions on buffer."""
        raise NotImplementedError


class Subactor:
    """Base class for specific actions the bot can perform."""

    REQUIRED_TYPES = {}
    VALID_TARGETS = []

    @classmethod
    def validate_params(cls, params):
        """Verify types of params."""
        for param, value in params.items():
            required_type = cls.REQUIRED_TYPES[param]
            if value and not isinstance(value, required_type):
                raise RuntimeError("Invalid type of parameter {} (expected {})"
                                   .format(param, required_type))

    def __init__(self, database, subreddit):
        """Initialize the Subactor class."""
        self.database = database
        self.cursor = database.cursor()
        self.subreddit = subreddit

    def action(self, post, mod, action_id):
        """Perform actions when command is matched."""
        pass


class Banner(Subactor):
    """A class to ban authors."""

    REQUIRED_TYPES = {'message': str, 'reason': str, 'duration': int}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    @staticmethod
    def _footer(target):
        """Return footer identifying the target that led to the ban."""
        if isinstance(target, praw.models.Comment):
            # praw.models.Comment.permalink is a method
            permalink = target.permalink()
            kind = "comment"
        else:
            permalink = target.permalink
            kind = "post"

        return ("\n\nThis action was taken because of the following {}: {}"
                ).format(kind, permalink)

    def __init__(self,
                 message=None,
                 reason=None,
                 duration=None,
                 *args,
                 **kwargs):
        """Initialize the banner class."""
        super().__init__(*args, **kwargs)
        self.message = message
        self.reason = reason
        self.duration = duration

    def action(self, post, mod, action_id):
        """Ban author of post."""
        message = self.message + self._footer(post)
        try:
            self.subreddit.banned.add(
                post.author,
                duration=self.duration,
                ban_message=message,
                ban_reason="{} - by {}".format(self.reason, mod)[:300])
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to ban %s: %s", post.author, exception)


class Locker(Subactor):
    """Locks posts, without necessarily removing them."""

    VALID_TARGETS = [praw.models.Submission]

    def action(self, post, mod, action_id):
        """Lock the post."""
        try:
            post.mod.lock()
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to lock %s: %s", post, exception)


class Notifier(Subactor):
    """A class for replying to targets."""

    REQUIRED_TYPES = {'text': str}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def __init__(self, text, *args, **kwargs):
        """Initialie the notifier class."""
        super().__init__(*args, **kwargs)
        self.text = text

    def _footer(self, url):
        """Return footer identifying bot as such."""
        base_reddit_url = self.subreddit._reddit.config.reddit_url
        sub_name = self.subreddit.display_name
        modmail_link = ("{base_url}/message/compose?to=%2Fr%2F{sub_name}"
                        "&message=Post%20in%20question:%20{url}").format(
                            base_url=base_reddit_url,
                            sub_name=sub_name,
                            url=urllib.parse.quote(url))

        return (
            "\n\n-----\n\nI am a bot. Please do not reply to this message, as "
            "it will go unread. Instead, [contact the moderators]({}) with "
            "questions or comments.").format(modmail_link)

    def action(self, post, mod, action_id):
        """Add, distinguish, and (if top-level) sticky reply to target."""
        permalink = post.permalink
        # praw.models.Comment.permalink is a method
        if isinstance(post, praw.models.Comment):
            permalink = permalink()
        text = self.text + self._footer(permalink)

        try:
            result = post.reply(text)
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to add comment on %s: %s", post.name,
                          exception)
            return
        else:
            self.log_notification(result, action_id)

        try:
            result.mod.distinguish(sticky=isinstance(post,
                                                     praw.models.Submission))
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to distinguish comment on %s: %s", post.name,
                          exception)

    def log_notification(self, comment, action_id):
        """Log notification, associating comment id with action."""
        _, comment_id = helpers.deserialize_thing_id(comment.fullname)
        self.cursor.execute('INSERT INTO notifications (comment_id, '
                            'action_id) VALUES(?,?)', (comment_id, action_id))


class Nuker(Subactor):
    """A class to recursiely remove replies.

    Does not affect the target itself. Submissions are skipped, but accepted
    for backwards compatibility.

    """

    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def action(self, post, mod, action_id):
        """Remove the replies."""
        if isinstance(post, praw.models.Submission):
            return

        try:
            post.refresh()
            post.replies.replace_more()
            flat_tree = post.replies.list()
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to retrieve comment tree on %s: %s",
                          post.name, exception)
            return

        for comment in flat_tree:
            if comment.distinguished is None:
                try:
                    comment.mod.remove()
                except prawcore.exceptions.RequestException as exception:
                    logging.error("Failed to remove comment %s: %s",
                                  comment.name, exception)


class ToolboxNoteAdderLedger(Ledger):
    """A class to manage buffered Toolbox updates."""

    EXPECTED_VERSION = 6

    @staticmethod
    def compress_blob(data_dict):
        """Return a blob from usernotes dict."""
        serialized_data = json.dumps(data_dict)
        compressed = zlib.compress(serialized_data.encode())
        base64_encoded = base64.b64encode(compressed)
        return base64_encoded.decode()

    @staticmethod
    def decompress_blob(blob):
        """Return dict from compressed usernote blob."""
        decoded = base64.b64decode(blob)
        unzipped = zlib.decompress(decoded)
        return json.loads(unzipped.decode())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.notes = []

    def _transform_page(self, content):
        usernotes_dict = json.loads(content)
        if usernotes_dict['ver'] != self.EXPECTED_VERSION:
            logging.error("Unexpected toolbox notes version: %s",
                          usernotes_dict['ver'])
            raise RuntimeError

        mod_list = usernotes_dict['constants']['users']
        mod_indices = {a: b for b, a in enumerate(mod_list)}
        warning_list = usernotes_dict['constants']['warnings']
        warning_indices = {a: b for b, a in enumerate(warning_list)}
        for note in self.notes:
            if note.mod not in mod_indices:
                mod_indices[note.mod] = len(mod_list)
                mod_list.append(note.mod)
            if note.level not in warning_indices:
                warning_indices[note.level] = len(warning_list)
                warning_list.append(note.level)

        data_dict = self.decompress_blob(usernotes_dict['blob'])

        for note in self.notes:
            serializable_note = note.to_serializable(mod_indices,
                                                     warning_indices)

            author_notes = data_dict.setdefault(note.author, {'ns': []})
            author_notes["ns"].insert(0, serializable_note)

        usernotes_dict['blob'] = self.compress_blob(data_dict)
        return json.dumps(usernotes_dict)

    def add(self, note):
        """Add a note to the buffer."""
        self.notes.append(note)

    def after(self):
        """Add queued reports to the wiki."""
        if not self.notes:
            return

        wiki_page = self.subreddit.wiki['usernotes']
        try:
            wiki_page.update(self._transform_page)
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to load toolbox usernotes: %s", exception)
            return
        else:
            self.notes.clear()


class ToolboxNoteAdder(Subactor):
    """A class to add Moderator Toolbox notes to the wiki."""

    LEDGER = ToolboxNoteAdderLedger
    REQUIRED_TYPES = {'level': str, 'text': str}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    @staticmethod
    def toolbox_link_string(thing):
        """Return thing's URL compressed in Toolbox's format."""
        if isinstance(thing, praw.models.Submission):
            return 'l,{submission_id}'.format(submission_id=thing.id)
        elif isinstance(thing, praw.models.Comment):
            return 'l,{submission_id},{comment_id}'.format(
                submission_id=thing.submission.id, comment_id=thing.id)

    def __init__(self, text, level, ledger, *args, **kwargs):
        """Initialize the ToolboxNoteAdder class."""
        super().__init__(*args, **kwargs)
        self.text = text
        self.level = level
        self.ledger = ledger

    def action(self, post, mod, action_id):
        """Enqueue a note to add after pass through the reports."""
        self.ledger.add(
            BufferedNote(
                str(post.author), self.level,
                self.toolbox_link_string(post), mod, self.text,
                int(time.time())))


class BufferedNote(
        namedtuple('BufferedNote', 'author level link mod text time')):
    """A class for buffered Toolbox usernotes."""
    __slots__ = ()

    def to_serializable(self, mod_indices, warning_indices):
        """Return a dict of a mod note, ready for insertion in the wiki."""
        return {
            "n": self.text,
            "t": self.time,
            "m": mod_indices[self.mod],
            "l": self.link,
            "w": warning_indices[self.level]
        }


class WikiWatcherLedger(Ledger):
    """A class to manage buffered AutoMod updates."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.placeholder_dict = {}

    def _transform_page(self, content):
        content = unescape(content)
        for placeholder, buffer in self.placeholder_dict.items():
            new_text = ", ".join([placeholder] + buffer)
            content = content.replace(placeholder, new_text)
        return content

    def add(self, placeholder, author):
        """Add author to the placeholder's buffer."""
        buffer = self.placeholder_dict.setdefault(placeholder, [])
        buffer.append(author)

    def after(self):
        """Add accumulated list of users to AutoMod config."""
        if not any(self.placeholder_dict.values()):
            return

        automod_config = self.subreddit.wiki['config/automoderator']

        try:
            automod_config.update(self._transform_page)
        except prawcore.exceptions.RequestException as exception:
            logging.error("Failed to update automod config %s", exception)
        else:
            for buffer in self.placeholder_dict.values():
                buffer.clear()


class WikiWatcher(Subactor):
    """A class for adding authors to AutoMod configuration lists."""

    LEDGER = WikiWatcherLedger
    REQUIRED_TYPES = {'placeholder': str}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def __init__(self, placeholder, ledger, *args, **kwargs):
        """Initialize the WikiWatcher class."""
        super().__init__(*args, **kwargs)
        self.placeholder = placeholder
        self.ledger = ledger

    def action(self, post, mod, action_id):
        """Add post author to buffer for update.

        Actual wiki update performed in WikiWatcher.after.

        """
        self.ledger.add(self.placeholder, str(post.author))
