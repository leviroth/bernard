import helpers
import logging
import praw
import urllib.parse
from xml.sax.saxutils import unescape


class Actor:
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
        return self.trigger.match(command) \
            and any(isinstance(post, target) for target in self.targets)

    def parse(self, command, mod, post):
        if self.match(command, post):
            action_id = self.log_action(post, mod)

            for subactor in self.subactors:
                subactor.action(post, mod, action_id=action_id)

            if self.remove:
                self.remove_thing(post, action_id=action_id)
            else:
                post.mod.approve()

            self.db.commit()

    def after(self):
        for subactor in self.subactors:
            subactor.after()

    def remove_thing(self, thing, action_id):
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
        target_type, target_id = helpers.deserialize_thing_id(target.fullname)
        action_summary = self.action_name
        action_details = self.action_details
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

        return self.cursor.lastrowid


class Subactor:
    def __init__(self, db, cursor, subreddit):
        self.db = db
        self.cursor = cursor
        self.subreddit = subreddit

    def action(self, post, mod, action_id):
        pass

    def after(self):
        pass


class Notifier(Subactor):
    def __init__(self, text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text

    def _footer(self, url):
        base_url = self.subreddit._reddit.config.reddit_url
        sub_name = self.subreddit.display_name
        modmail_link = (
            "{base_url}/message/compose?to=%2Fr%2F{sub_name}"
            "&message=Post%20in%20question:%20{url}"
        ).format(base_url=base_url,
                 sub_name=sub_name,
                 url=urllib.parse.quote(url))

        return (
            "\n\n-----\n\nI am a bot. Please do not reply to this message, as"
            "it will go unread. Instead, [contact the moderators]({}) with "
            "questions or comments."
        ).format(modmail_link)


    def action(self, post, mod, action_id):
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
            # Perhaps we should log the notification in the controller, not in
            # this class

        try:
            result.mod.distinguish(sticky=isinstance(post,
                                                     praw.models.Submission))
        except Exception as e:
            logging.error("Failed to distinguish comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))

    def log_notification(self, parent, comment, action_id):
        _, comment_id = helpers.deserialize_thing_id(comment.fullname)
        self.cursor.execute('INSERT INTO notifications (comment_id, '
                            'action_id) VALUES(?,?)', (comment_id, action_id))


class WikiWatcher(Subactor):
    def __init__(self, placeholder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.placeholder = placeholder
        self.to_add = []

    def action(self, post, mod, action_id):
        self.to_add.append(str(post.author))

    def after(self):
        """Add accumulated list of users to AutoMod config"""
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
    def __init__(self, message, reason, duration=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.reason = reason
        self.duration = duration

    def action(self, post, mod, action_id):
        try:
            self.subreddit.banned.add(
                post.author, duration=self.duration, ban_message=self.message,
                ban_reason="{} - by {}".format(self.reason, mod)[:300]
            )
        except Exception as e:
            logging.error("Failed to ban {user}: {err}"
                          .format(user=post.author, err=e))


class Nuker(Subactor):
    def action(self, post, mod, action_id):
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


registry = {
    'notify': Notifier,
    'wikiwatch': WikiWatcher,
    'ban': Banner,
    'nuke': Nuker
}
