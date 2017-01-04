import logging
import praw
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

    def parse(self, command, post, mod):
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
        for actor in self.actors:
            actor.after()

    def remove_thing(self, thing):
        try:
            thing.remove()
        except Exception as e:
            logging.error("Failed to remove {thing}: {err}"
                          .format(thing=thing, err=e))

        if isinstance(thing, praw.models.Submission):
            try:
                thing.lock()
            except Exception as e:
                logging.error("Failed to lock {thing}: {err}"
                              .format(thing=thing, err=e))

        self.cur.execute('SELECT max(id) FROM actions')
        action_id = self.cur.fetchone()[0]
        self.cur.execute('INSERT INTO removals (action_id) VALUES(?)',
                         (action_id,))

    def deserialize_thing_id(thing_id):
        return tuple(int(x, base=36) for x in thing_id[1:].split('_'))

    def log_action(self, target, moderator):
        target_type, target_id = self.deserialize_thing_id(target.fullname)
        action_summary = self.action_name
        action_details = self.action_details
        _, author_id = self.deserialize_thing_id(target.author.fullname)
        self.cur.execute('INSERT IGNORE INTO users (id, username) '
                         'VALUES(?,?)', (author_id, target.author.fullname))
        self.cur.execute('SELECT id FROM moderators WHERE username=?',
                         moderator)
        moderator_id = self.cur.fetchone()[0]
        _, subreddit = self.deserialize_thing_id(self.subreddit.fullname)
        self.cur.execute(
            'INSERT INTO actions (target_type, target_id, action_summary, '
            'action_details, author, moderator, subreddit) '
            'VALUES(?,?,?,?,?,?,?)',
            (target_type, target_id, action_summary, action_details, author_id,
             moderator_id, subreddit)
        )
        return self.cur.lastrowid


class Subactor:
    def __init__(self, db, cursor, subreddit):
        self.db = db
        self.cur = cursor
        self.subreddit = subreddit

    def action(self, post, mod):
        pass

    def after(self):
        pass


class Notifier(Subactor):
    def __init__(self, note_text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.note_text = note_text

    def action(self, post, mod):
        try:
            result = post.reply(self.note_text)
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
        self.cur.execute('SELECT max(id) FROM actions')
        action_id = self.cur.fetchone()[0]
        self.cur.execute('INSERT INTO notifications (comment_id, action_id) '
                         'VALUES(?,?)', (comment_id, action_id))


class Shadowbanner(Subactor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.to_ban = []

    def action(self, post, mod):
        print(mod + ' is shadowbanning ' + str(post.author))

        try:
            post.remove()
        except Exception as e:
            logging.error("Failed to remove {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
        else:
            self.to_ban.append((str(post.author), post.permalink))

    def after(self):
        """Ban accumulated list of users"""

        if not self.to_ban:
            return

        names = ', '.join([a for (a, b) in self.to_ban])
        reasons = '\n'.join(['#' + ': '.join(a) for a in self.to_ban])

        try:
            automod_config = self.sub.get_wiki_page(self.sub,
                                                    'config/automoderator')
        except Exception as e:
            logging.error("Failed to load automod list of bans: {err}"
                          .format(err=str(e)))
            return

        new_content = unescape(automod_config.content_md)
        new_content = new_content.replace('#do_not_remove_a', reasons +
                                          '\n#do_not_remove_a')
        new_content = new_content.replace('do_not_remove_b',
                                          'do_not_remove_b, ' + names)

        try:
            self.sub.edit_wiki_page(self.sub,
                                    'config/automoderator',
                                    new_content, "bans")
        except Exception as e:
            logging.error("Failed to update bans {err}".format(err=str(e)))
            return
        else:
            self.to_ban = []


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
    'shadowban': Shadowbanner,
    'ban': Banner,
    'nuke': Nuker
}
