import base64
import json
import logging
import praw
import prawcore
import time
import urllib.parse
import zlib
from xml.sax.saxutils import unescape

from . import helpers


class Actor:
    """A class for managing rules.

    Responsible for matching input with commands, performing the requested
    actions, and logging to database.

    """
    def __init__(self, trigger, targets, remove, subactors, action_name,
                 action_details, db, cursor, subreddit):
        self.trigger = trigger
        self.targets = targets
        self.remove = remove
        self.subactors = subactors
        self.action_name = action_name
        self.action_details = action_details
        self.db = db
        self.cursor = cursor
        self.subreddit = subreddit

    def match(self, command, post):
        "Return true if command matches and post is the right type of thing."
        return self.trigger.match(command) \
            and any(isinstance(post, target) for target in self.targets)

    def parse(self, command, mod, post):
        "Execute requested actions if report matches command."
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

            self.db.commit()

    def after(self):
        "Perform end-of-loop actions for each subactor."
        for subactor in self.subactors:
            subactor.after()

    def remove_thing(self, thing, action_id):
        "Perform and log removal. Lock if thing is a submission."
        try:
            thing.mod.remove()
        except Exception as e:
            logging.error("Failed to remove {thing}: {err}"
                          .format(thing=thing, err=e))

        if isinstance(thing, praw.models.Submission):
            try:
                thing.mod.lock()
            except Exception as e:
                logging.error("Failed to lock {thing}: {err}"
                              .format(thing=thing, err=e))

        self.cursor.execute('INSERT INTO removals (action_id) VALUES(?)',
                            (action_id,))

    def log_action(self, target, moderator):
        "Log action in database and console. Return database row id."
        target_type, target_id = helpers.deserialize_thing_id(target.fullname)
        action_summary = self.action_name
        action_details = self.action_details

        # Get (or create) database entries for author and moderator
        self.cursor.execute('INSERT OR IGNORE INTO users (username) '
                            'VALUES(?)', (target.author.name,))
        self.cursor.execute('SELECT id FROM users WHERE username = ?',
                            (target.author.name,))
        author_id = self.cursor.fetchone()[0]
        self.cursor.execute('INSERT OR IGNORE INTO users (username) '
                            'VALUES(?)', (moderator,))
        self.cursor.execute('SELECT id FROM users WHERE username = ?',
                            (moderator,))
        moderator_id = self.cursor.fetchone()[0]

        _, subreddit = helpers.deserialize_thing_id(self.subreddit.fullname)

        self.cursor.execute(
            'INSERT INTO actions (target_type, target_id, action_summary, '
            'action_details, author, moderator, subreddit) '
            'VALUES(?,?,?,?,?,?,?)',
            (target_type, target_id, action_summary, action_details, author_id,
             moderator_id, subreddit)
        )

        print(moderator, action_summary, action_details, target,
              self.subreddit)

        return self.cursor.lastrowid


class Subactor:
    "Base class for specific actions the bot can perform."
    def __init__(self, db, cursor, subreddit):
        self.db = db
        self.cursor = cursor
        self.subreddit = subreddit

    def action(self, post, mod, action_id):
        "Called immediately when a command is matched."
        pass

    def after(self):
        "Called after checking all reports to enable batch actions."
        pass


class Notifier(Subactor):
    "A class for replying to targets."
    def __init__(self, text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text

    def _footer(self, url):
        "Return footer identifying bot as such and directing users to modmail."
        base_reddit_url = self.subreddit._reddit.config.reddit_url
        sub_name = self.subreddit.display_name
        modmail_link = (
            "{base_url}/message/compose?to=%2Fr%2F{sub_name}"
            "&message=Post%20in%20question:%20{url}"
        ).format(base_url=base_reddit_url,
                 sub_name=sub_name,
                 url=urllib.parse.quote(url))

        return (
            "\n\n-----\n\nI am a bot. Please do not reply to this message, as "
            "it will go unread. Instead, [contact the moderators]({}) with "
            "questions or comments."
        ).format(modmail_link)

    def action(self, post, mod, action_id):
        "Add, distinguish, and (if top-level) sticky reply to target."
        permalink = post.permalink
        # praw.models.Comment.permalink is a method
        if isinstance(post, praw.models.Comment):
            permalink = permalink()
        text = self.text + self._footer(permalink)

        try:
            result = post.reply(text)
        except Exception as e:
            logging.error("Failed to add comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
            return
        else:
            self.log_notification(post, result, action_id)

        try:
            result.mod.distinguish(sticky=isinstance(post,
                                                     praw.models.Submission))
        except Exception as e:
            logging.error("Failed to distinguish comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))

    def log_notification(self, parent, comment, action_id):
        "Log notification, associating comment id with action."
        _, comment_id = helpers.deserialize_thing_id(comment.fullname)
        self.cursor.execute('INSERT INTO notifications (comment_id, '
                            'action_id) VALUES(?,?)', (comment_id, action_id))


class WikiWatcher(Subactor):
    "A class for adding authors to AutoMod configuration lists."
    def __init__(self, placeholder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.placeholder = placeholder
        self.to_add = []

    def action(self, post, mod, action_id):
        """Add author to local list of users. Actual wiki update performed in
        WikiWatcher.after.

        """
        self.to_add.append(str(post.author))

    def after(self):
        "Add accumulated list of users to AutoMod config."
        if not self.to_add:
            return

        names = ', '.join(self.to_add)

        try:
            automod_config = self.subreddit.wiki['config/automoderator']
        except Exception as e:
            logging.error("Failed to load automod config: {err}"
                          .format(err=e))
            return

        new_content = unescape(automod_config.content_md)
        new_content = new_content.replace(
            self.placeholder,
            '{placeholder}, {names}'
            .format(placeholder=self.placeholder, names=names)
        )

        try:
            automod_config.edit(new_content)
        except Exception as e:
            logging.error("Failed to update automod config {err}"
                          .format(err=e))
            return
        else:
            self.to_add = []


class Banner(Subactor):
    "A class to ban authors."
    def __init__(self, message, reason, duration=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.reason = reason
        self.duration = duration

    def action(self, post, mod, action_id):
        "Ban author of post."
        try:
            self.subreddit.banned.add(
                post.author, duration=self.duration, ban_message=self.message,
                ban_reason="{} - by {}".format(self.reason, mod)[:300]
            )
        except Exception as e:
            logging.error("Failed to ban {user}: {err}"
                          .format(user=post.author, err=e))


class Nuker(Subactor):
    """A class to recursiely remove replies.

    Does not affect the target itself.

    """
    def action(self, post, mod, action_id):
        "Remove the replies."
        try:
            post.refresh()
            post.replies.replace_more()
            flat_tree = post.replies.list() + [post]
        except Exception as e:
            logging.error("Failed to retrieve comment tree on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
            return

        for comment in flat_tree:
            if comment.distinguished is None:
                try:
                    comment.mod.remove()
                except Exception as e:
                    logging.error("Failed to remove comment {thing}: {err}"
                                  .format(thing=comment.name, err=str(e)))


class ToolboxNoteAdder(Subactor):
    """A class to add Moderator Toolbox notes to the wiki."""
    EXPECTED_VERSION = 6

    def __init__(self, text, level, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text
        self.level = level
        self.to_add = []

    def action(self, post, mod, action_id):
        """Enqueue a note to add after pass through the reports."""
        author = str(post.author)
        now = int(time.time())
        link = self.toolbox_link_string(post)
        self.to_add.append((author, link, now, mod))

    def after(self):
        """Add queued reports to the wiki."""
        if not self.to_add:
            return

        wiki_page = self.subreddit.wiki['usernotes']
        try:
            usernotes_dict = self.fetch_notes_dict(wiki_page)
        except prawcore.exceptions.RequestException as e:
            logging.error("Failed to load toolbox usernotes: {err}"
                          .format(err=e))
            return

        if usernotes_dict['ver'] != self.EXPECTED_VERSION:
            return

        # Mods and warning levels are stored in these lists, but referenced in
        # notes via their indices. Modifications to these lists are persisted
        # on the wiki.
        mod_list = usernotes_dict['constants']['users']
        mod_indices = {a: b for b, a in enumerate(mod_list)}
        warning_list = usernotes_dict['constants']['warnings']
        warning_indices = {a: b for b, a in enumerate(warning_list)}
        if self.level not in warning_indices:
            warning_indices[self.level] = len(warning_list)
            warning_list.append(self.level)

        data_dict = self.decompress_blob(usernotes_dict['blob'])

        for author, link, timestamp, mod in self.to_add:
            if mod not in mod_indices:
                mod_indices[mod] = len(mod_list)
                mod_list.append(mod)

            note = self.build_note(timestamp, mod_indices[mod], link,
                                   warning_indices[self.level])

            if author not in data_dict:
                data_dict[author] = {"ns": []}

            data_dict[author]["ns"].insert(0, note)

        usernotes_dict['blob'] = self.compress_blob(data_dict)
        serialized_page = json.dumps(usernotes_dict)

        try:
            wiki_page.edit(serialized_page)
        except prawcore.exceptions.RequestException as e:
            logging.error("Failed to update automod config {err}"
                          .format(err=e))
            return
        else:
            self.to_add = []

    def build_note(self, timestamp, mod_index, link, warning_index):
        """Return a dict of a mod note, ready for insertion in the wiki."""
        return {
            "n": self.text,
            "t": timestamp,
            "m": mod_index,
            "l": link,
            "w": warning_index
        }

    def compress_blob(self, data_dict):
        """Return a blob from usernotes dict."""
        serialized_data = json.dumps(data_dict)
        compressed = zlib.compress(serialized_data.encode())
        base64_encoded = base64.b64encode(compressed)
        return base64_encoded.decode()

    def decompress_blob(self, blob):
        """Return dict from compressed usernote blob."""
        decoded = base64.b64decode(blob)
        unzipped = zlib.decompress(decoded)
        return json.loads(unzipped.decode())

    def fetch_notes_dict(self, wiki_page):
        """Fetch usernotes dict from wiki.

        Uses network connection; may therefore raise
        prawcore.exceptions.RequestException.

        """
        usernotes_json = wiki_page.content_md
        return json.loads(usernotes_json)

    def toolbox_link_string(self, thing):
        """Return thing's URL compressed in Toolbox's format."""
        if isinstance(thing, praw.models.Submission):
            return 'l,{submission_id}'.format(submission_id=thing.id)
        elif isinstance(thing, praw.models.Comment):
            return 'l,{submission_id},{comment_id}'.format(
                submission_id=thing.submission.id, comment_id=thing.id)
