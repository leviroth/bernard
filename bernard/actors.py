import logging
import praw
from xml.sax.saxutils import unescape


class Actor:
    def __init__(self, trigger, targets, remove, subactors, action_name,
                 action_details, db):
        self.trigger = trigger
        self.targets = targets
        self.remove = remove
        self.subactors = subactors
        self.action_name = action_name
        self.action_details = action_details
        self.db = db

    def match(self, command, post):
        return self.trigger.match(command) \
            and any(isinstance(post, target) for target in self.targets)

    def parse(self, command, post, mod):
        if self.match(command, post):
            for subactor in self.subactors:
                subactor.action(post, mod)

            if self.remove:
                post.remove()
            else:
                post.approve()

            self.log_action(post, mod)

    def after(self):
        for actor in self.actors:
            actor.after()

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
        self.db.commit()
        return self.cur.lastrowid


class Subactor():
    def __init__(self, db, cursor):
        self.db = db
        self.cur = cursor

    def action(self, post, mod):
        pass

    def after(self):
        pass

    def log_notification(self, parent, comment):
        self.cur.execute('INSERT INTO notifications (parent, comment) '
                         'VALUES(?,?)', (parent.fullanme, comment.fullname))
        self.db.commit()


class Remover(Subactor):
    def action(self, post, mod):
        try:
            post.remove()
        except Exception as e:
            logging.error("Failed to remove {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
            return False

        try:
            post.lock()
        except Exception as e:
            logging.error("Failed to lock {thing}: {err}"
                          .format(thing=post.name, err=str(e)))

        return True

    def log_action(self, action_id):
        self.cur.execute('INSERT INTO removals (action_id) VALUES(?)',
                         (action_id,))
        self.db.commit()


class Notifier(Subactor):
    def __init__(self, note_text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.note_text = note_text

    def _add_reply(thing, text):
        if isinstance(thing, praw.objects.Submission):
            return thing.add_comment(text)
        else:
            return thing.reply(text)

    def action(self, post, mod):
        try:
            result = self._add_reply(post, self.note_text)
        except Exception as e:
            logging.error("Failed to add comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
            return
        else:
            self.log_notification(post, result)
            # Perhaps we should log the notification in the controller, not in
            # this class

        try:
            result.distinguish(sticky=isinstance(post,
                                                 praw.objects.Submission))
        except Exception as e:
            logging.error("Failed to distinguish comment on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))


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
    def __init__(self, message, reason, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message = message
        self.reason = reason

    def action(self, post, mod):
        try:
            self.sub.add_ban(post.author, duration=3,
                             ban_message=self.message,
                             ban_reason=self.reason + " - by " + mod)
        except Exception as e:
            logging.error("Failed to ban {user}: {err}"
                          .format(user=post.author, err=e))


class Warner(Subactor):
    def __init__(self, rule, note_text, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.rule might not be needed
        self.rule = rule
        self.note_text = note_text

    def action(self, post, mod):
        self.cur.execute('SELECT * FROM warnings WHERE target = ?',
                         (post.fullname,))
        # Assumption: We can keep a table for all warnings, since a thread
        # should never need more than one
        if len(self.browser.cur.fetchall()):
            return

        note_text = self.note_text

        try:
            result = post.add_comment(note_text)
        except Exception as e:
            logging.error("Failed to add comment on {thing}: {err}"
                          .format(thing=post.name, err=e))
            return

        self.cur.execute('INSERT INTO warnings (target) VALUES (?)',
                         (post.fullname,))
        self.db.commit()

        try:
            post.approve()
            result.distinguish(sticky=True)
        except Exception as e:
            logging.error("Failed to distinguish comment on {thing}: {err}"
                          .format(thing=post.fullname, err=str(e)))


class Nuker(Subactor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def action(self, post, mod):
        try:
            tree = praw.objects.Submission.from_url(self.sub, post.permalink)
            tree.replace_more_comments()
        except Exception as e:
            logging.error("Failed to retrieve comment tree on {thing}: {err}"
                          .format(thing=post.name, err=str(e)))
            return

        comments = praw.helpers.flatten_tree(tree.comments)
        for comment in comments:
            if comment.distinguished is None:
                try:
                    comment.remove()
                except Exception as e:
                    logging.error("Failed to remove comment {thing}: {err}"
                                  .format(thing=comment.name, err=str(e)))


registry = {
    'remove': Remover,
    'notify': Notifier,
    'shadowban': Shadowbanner,
    'ban': Banner,
    'warn': Warner,
    'nuke': Nuker
}
