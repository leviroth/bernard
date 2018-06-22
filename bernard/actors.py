"""Classes that carry out specific actions on posts and comments."""
import base64
import json
import logging
import time
import urllib.parse
import zlib
from collections import deque, namedtuple
from xml.sax.saxutils import unescape

import praw
import prawcore
import prawdditions  # NOQA

from . import helpers


class Rule:
    """A class for managing rules.

    Responsible for matching input with commands, performing the requested
    actions, and logging to database.

    """

    def __init__(self, commands, targets, remove, lock, actors, action_name,
                 action_details, database, subreddit):
        """Initialize the Actor class."""
        self.commands = commands
        self.targets = targets
        self.remove = remove
        self.lock = lock
        self.actors = actors
        self.action_name = action_name
        self.action_details = action_details
        self.database = database
        self.cursor = database.cursor()
        self.subreddit = subreddit

    def _already_acted(self, fullname, mod):
        target_type, target_id = helpers.deserialize_thing_id(fullname)

        self.cursor.execute('SELECT 1 FROM actions INNER JOIN users '
                            'ON actions.moderator = users.id '
                            'WHERE target_type = ? AND target_id = ? '
                            'AND users.username = ?',
                            (target_type, target_id, str(mod)))
        result = self.cursor.fetchone() is not None

        if result:
            # Logging to see where we act on the same thing twice
            self.cursor.execute('SELECT users.username FROM actions '
                                'INNER JOIN users '
                                'ON actions.moderator = users.id '
                                'WHERE target_type = ? AND target_id = ?',
                                (target_type, target_id))
            previous = self.cursor.fetchall()
            if len(previous) > 0:
                logging.info("Saw repeated actions on %s", fullname)

        return result

    def match(self, report, thing):
        """Return true if command matches and thing is the right type."""
        return any(report.casefold() == command for command in self.commands) \
            and any(isinstance(thing, target) for target in self.targets)

    def parse(self, command, mod, post):
        """Execute requested actions if report matches command."""
        if self.match(command, post):
            # Only act once on a given thing
            if self._already_acted(post.fullname, mod):
                return

            self.log_action(post, mod)

            for actor in self.actors:
                actor.action(post, mod)

            if self.remove:
                try:
                    post.mod.remove()
                except prawcore.PrawcoreException as exception:
                    logging.error("Failed to remove %s: %s", post, exception)
            else:
                try:
                    post.mod.approve()
                except prawcore.PrawcoreException as exception:
                    logging.error("Failed to approve %s: %s", post, exception)

            if self.lock and isinstance(post, praw.models.Submission):
                try:
                    post.mod.lock()
                except prawcore.PrawcoreException as exception:
                    logging.error("Failed to lock %s: %s", post, exception)

            self.database.commit()

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


class ActionBuffer:  # pylint: disable=too-few-public-methods
    """Abstract class for managing buffered updates."""

    def __init__(self, subreddit):
        """Initialize the ActionBuffer class."""
        self.subreddit = subreddit

    def after(self):
        """Perform actions on buffer."""
        raise NotImplementedError


class Actor:
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

    def __init__(self, subreddit):
        """Initialize the Actor class."""
        self.subreddit = subreddit

    def action(self, post, mod):
        """Perform actions when command is matched."""
        pass


class Banner(Actor):
    """A class to ban authors."""

    REQUIRED_TYPES = {'message': str, 'reason': str, 'duration': int}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]
    KINDS = {praw.models.Comment: 'comment', praw.models.Submission: 'post'}

    @classmethod
    def _footer(cls, target):
        """Return footer identifying the target that led to the ban."""
        kind = cls.KINDS[type(target)]

        permalink = urllib.parse.quote(target.permalink)

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

    def action(self, post, mod):
        """Ban author of post."""
        message = self.message + self._footer(post)
        try:
            self.subreddit.banned.add(
                post.author,
                duration=self.duration,
                ban_message=message,
                ban_reason="{} - by {}".format(self.reason, mod)[:300])
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to ban %s: %s", post.author, exception)


class Locker(Actor):
    """Locks posts, without necessarily removing them."""

    VALID_TARGETS = [praw.models.Submission]

    def action(self, post, mod):
        """Lock the post."""
        try:
            post.mod.lock()
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to lock %s: %s", post, exception)


class Modmailer(Actor):
    """A class for sending modmail to authors."""

    REQUIRED_TYPES = {'subject': str, 'body': str}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def __init__(self, subject, body, *args, **kwargs):
        """Initialie the Modmailer class."""
        super().__init__(*args, **kwargs)
        self.subject = subject
        self.body = body

    def action(self, post, mod):
        """Add, distinguish, and (if top-level) sticky reply to target."""
        try:
            self.subreddit.modmail.create(self.subject, self.body,
                                          post.author, author_hidden=True)
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to send modmail on %s: %s", post.name,
                          exception)
            return


class Notifier(Actor):
    """A class for replying to targets."""

    REQUIRED_TYPES = {'text': str}
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def __init__(self, text, *args, **kwargs):
        """Initialize the Notifier class."""
        super().__init__(*args, **kwargs)
        self.text = text

    def _footer(self, url):
        """Return footer identifying bot as such."""
        base_reddit_url = self.subreddit._reddit.config.reddit_url
        sub_name = self.subreddit.display_name

        escaped_url = urllib.parse.quote(base_reddit_url + url)

        modmail_link = ("{base_url}/message/compose?to=%2Fr%2F{sub_name}"
                        "&message=Post%20in%20question:%20{url}").format(
                            base_url=base_reddit_url,
                            sub_name=sub_name,
                            url=escaped_url)

        return (
            "\n\n-----\n\nI am a bot. Please do not reply to this message, as "
            "it will go unread. Instead, [contact the moderators]({}) with "
            "questions or comments.").format(modmail_link)

    def action(self, post, mod):
        """Add, distinguish, and (if top-level) sticky reply to target."""
        permalink = post.permalink
        text = self.text + self._footer(permalink)

        try:
            result = post.reply(text)
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to add comment on %s: %s", post.name,
                          exception)
            return
        except praw.exceptions.APIException:
            logging.error("Too old to reply: %s", post.name)
            return

        try:
            result.mod.distinguish(sticky=isinstance(post,
                                                     praw.models.Submission))
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to distinguish comment on %s: %s", post.name,
                          exception)


class NukerActionBuffer(ActionBuffer):
    """A buffer for enqueued comment removals."""

    def __init__(self, *args, **kwargs):
        """Initialize the NukerActionBuffer class."""
        super().__init__(*args, **kwargs)
        self.actions = deque()

    def add(self, comment):
        """Enqueue a comment to be removed."""
        self.actions.append(comment)

    def after(self):
        """Add a comment to the queue.

        All comments in the queue will be removed, so it's probably best to
        check if a comment is distinguished before adding it.

        """
        for _ in range(30):
            if len(self.actions) == 0:
                return
            comment = self.actions.popleft()
            try:
                comment.mod.remove()
            except prawcore.PrawcoreException as exception:
                logging.error("Failed to remove comment %s: %s",
                              comment.name, exception)


class Nuker(Actor):
    """A class to recursiely remove replies.

    Does not affect the target itself. Submissions are skipped, but accepted
    for backwards compatibility.

    """

    ACTION_BUFFER = NukerActionBuffer
    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def __init__(self, action_buffer, *args, **kwargs):
        """Initialize the Nuker class."""
        super().__init__(*args, **kwargs)
        self.action_buffer = action_buffer

    def action(self, post, mod):
        """Remove the replies."""
        if isinstance(post, praw.models.Submission):
            return

        try:
            post.refresh()
            post.replies.replace_more()
            flat_tree = post.replies.list()
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to retrieve comment tree on %s: %s",
                          post.name, exception)
            return

        for comment in flat_tree:
            if comment.distinguished is None:
                self.action_buffer.add(comment)


class ToolboxNoteAdderActionBuffer(ActionBuffer):
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
        """Initialize the ToolboxNoteAdderActionBuffer class."""
        super().__init__(*args, **kwargs)
        self.notes = []

    def _prepare_indices(self, items, attr):
        indices = {a: b for b, a in enumerate(items)}
        for note in self.notes:
            value = getattr(note, attr)
            if value not in indices:
                indices[value] = len(items)
                items.append(value)
        return indices

    def _transform_page(self, content):
        usernotes_dict = json.loads(content)
        if usernotes_dict['ver'] != self.EXPECTED_VERSION:
            logging.error("Unexpected toolbox notes version: %s",
                          usernotes_dict['ver'])
            raise RuntimeError

        mod_list = usernotes_dict['constants']['users']
        mod_indices = self._prepare_indices(mod_list, 'mod')
        warning_list = usernotes_dict['constants']['warnings']
        warning_indices = self._prepare_indices(warning_list, 'level')

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
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to load toolbox usernotes: %s", exception)
            return
        else:
            self.notes.clear()


class ToolboxNoteAdder(Actor):
    """A class to add Moderator Toolbox notes to the wiki."""

    ACTION_BUFFER = ToolboxNoteAdderActionBuffer
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

    def __init__(self, text, level, action_buffer, *args, **kwargs):
        """Initialize the ToolboxNoteAdder class."""
        super().__init__(*args, **kwargs)
        self.text = text
        self.level = level
        self.action_buffer = action_buffer

    def action(self, post, mod):
        """Enqueue a note to add after pass through the reports."""
        self.action_buffer.add(
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


class AutomodWatcherActionBuffer(ActionBuffer):
    """A class to manage buffered AutoMod updates."""

    def __init__(self, *args, **kwargs):
        """Initialize the AutomodWatcherActionBuffer class."""
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
        except prawcore.PrawcoreException as exception:
            logging.error("Failed to update automod config %s", exception)
        else:
            for buffer in self.placeholder_dict.values():
                buffer.clear()


class AutomodWatcher(Actor):
    """An abstract class for adding items to AutoMod configuration lists."""

    ACTION_BUFFER = AutomodWatcherActionBuffer
    REQUIRED_TYPES = {'placeholder': str}

    def __init__(self, placeholder, action_buffer, *args, **kwargs):
        """Initialize the AutomodWatcher class."""
        super().__init__(*args, **kwargs)
        self.placeholder = placeholder
        self.action_buffer = action_buffer

    def _get_item(self, post):
        """Return item to add to automod."""
        raise NotImplementedError

    def action(self, post, mod):
        """Add item to buffer for update.

        Actual wiki update performed in AutomodWatcherActionBuffer.after.

        """
        self.action_buffer.add(self.placeholder, self._get_item(post))


class AutomodDomainWatcher(AutomodWatcher):
    """An class for adding domains to AutoMod configuration lists."""

    VALID_TARGETS = [praw.models.Submission]

    def _get_item(self, post):
        """Return post's author."""
        return post.domain


class AutomodUserWatcher(AutomodWatcher):
    """An class for adding authors to AutoMod configuration lists."""

    VALID_TARGETS = [praw.models.Submission, praw.models.Comment]

    def _get_item(self, post):
        """Return post's author."""
        return str(post.author)
