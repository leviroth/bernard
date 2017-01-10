from . import helpers
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
            self.log_action(post, mod)

            for subactor in self.subactors:
                subactor.action(post, mod)

            if self.remove:
                self.remove_thing(post)
            else:
                post.mod.approve()

            self.db.commit()

    def after(self):
        for subactor in self.subactors:
            subactor.after()

    def remove_thing(self, thing):
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

        self.cursor.execute('SELECT max(id) FROM actions')
        action_id = self.cursor.fetchone()[0]
        self.cursor.execute('INSERT INTO removals (action_id) VALUES(?)',
                            (action_id,))

    def log_action(self, target, moderator):
        target_type, target_id = helpers.deserialize_thing_id(target.fullname)
        action_summary = self.action_name
        action_details = self.action_details
        _, author_id = helpers.deserialize_thing_id(target.author.fullname)
        self.cursor.execute('INSERT OR IGNORE INTO users (id, username) '
                            'VALUES(?,?)', (author_id, target.author.fullname))
        self.cursor.execute('SELECT id FROM users WHERE username=?',
                            (moderator,))
        try:
            moderator_id = self.cursor.fetchone()[0]
        except TypeError:
            moderator_id_str = self.subreddit._reddit.user(moderator).fullname
            _, moderator_id = helpers.deserialize_thing_id(moderator_id_str)
        _, subreddit = helpers.deserialize_thing_id(self.subreddit.fullname)
        self.cursor.execute(
            'INSERT INTO actions (target_type, target_id, action_summary, '
            'action_details, author, moderator, subreddit) '
            'VALUES(?,?,?,?,?,?,?)',
            (target_type, target_id, action_summary, action_details, author_id,
             moderator_id, subreddit)
        )


class Subactor:
    def __init__(self, db, cursor, subreddit):
        self.db = db
        self.cursor = cursor
        self.subreddit = subreddit

    def action(self, post, mod):
        pass

    def after(self):
        pass


class Notifier(Subactor):
    def __init__(self, text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = text

    def action(self, post, mod):
        url = urllib.parse.quote(post.permalink.encode('utf-8'))
        text = self.text.replace('{url}', url)
        try:
            result = post.reply(text)
        except Exception as e:
            logging.error("Failed to add comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
            return
        else:
            self.log_notification(post, result)
            # Perhaps we should log the notification in the controller, not in
            # this class

        try:
            result.mod.distinguish(sticky=isinstance(post,
                                                     praw.models.Submission))
        except Exception as e:
            logging.error("Failed to distinguish comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))

    def log_notification(self, parent, comment):
        comment_id = int(comment.fullname.split('_')[1], 36)
        self.cursor.execute('SELECT max(id) FROM actions')
        action_id = self.cursor.fetchone()[0]
        self.cursor.execute('INSERT INTO notifications (comment_id, '
                            'action_id) VALUES(?,?)', (comment_id, action_id))


class WikiWatcher(Subactor):
    def __init__(self, placeholder, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.placeholder = placeholder
        self.to_add = []

    def action(self, post, mod):
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

    def action(self, post, mod):
        try:
            self.subreddit.banned.add(
                post.author, duration=self.duration, ban_message=self.message,
                ban_reason="{} - by {}".format(self.reason, mod)[:300]
            )
        except Exception as e:
            logging.error("Failed to ban {user}: {err}"
                          .format(user=post.author, err=e))


class Nuker(Subactor):
    def action(self, post, mod):
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
