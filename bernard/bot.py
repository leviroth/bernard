import praw
import json
import urllib2
import re
import time
import sqlite3
from xml.sax.saxutils import unescape

class Checker:
    def __init__(self, browser):
        self.browser = browser

    def check(self, report):
        result = self.regex.match(report)

        if result is not None:
            return result.groupdict()
        else:
            return None

    def action(self, post, mod, rule=None, note_text=None):
        if rule is None:
            rule = self.rule
        if note_text is None:
            note_text = self.note_text

        try:
            post.remove()
        except Exception as e:
            print "- Failed to remove " + post.fullname
            print str(e)
            return

        log_text = mod + " removed " + post.fullname + " by " + \
            str(post.author) + " [" + rule + "]"
        print log_text
        self.browser.cur.execute('INSERT INTO actions (mod, action, reason) VALUES(?,?,?)',
                    (mod, "removed " + post.fullname + " by " +
                     str(post.author), rule))
        self.browser.sql.commit()

        # Build note text

        content_list = []
        if self.header:
            content_list.append(self.browser.header)
        content_list.append(note_text)
        if self.footer:
            content_list.append(
                self.browser.footer.replace(
                    "{url}", urllib2.quote(post.permalink.encode('utf8'))
                    )
                )
        note_text = "\n\n".join(content_list)

        try:
            post.lock()
        except Exception as e:
            print "- Failed to lock " + post.fullname
            print str(e)

        try:
            result = post.add_comment(note_text)
        except Exception as e:
            print "- Failed to add comment on " + post.fullname
            print str(e)
            return
        else:
            self.browser.cur.execute('INSERT INTO notifications '
                    '(target, comment) VALUES(?,?)',
                    (post.fullname, result.fullname))
            self.browser.sql.commit()

        try:
            result.distinguish(sticky=True)
        except Exception as e:
            print "* Failed to distinguish comment on " + post.fullname
            print str(e)

    def after(self):
        pass


class ShadowBanner(Checker):
    def __init__(self, browser):
        self.to_ban = []
        self.regex = re.compile("^(shadowban|sb)$", re.I)
        self.types = set([praw.objects.Submission, praw.objects.Comment])
        Checker.__init__(self, browser)

    def action(self, post, mod):
        print mod + ' is shadowbanning ' + str(post.author)

        try:
            post.remove()
        except Exception as e:
            print "- Failed to remove " + post.fullname
            print str(e)
        else:
            self.to_ban.append((str(post.author), post.permalink))

            self.browser.cur.execute('INSERT INTO actions (mod, action, reason) '
                        'VALUES(?,?,?)', (mod, 'banned ' + str(post.author),
                                          post.permalink))
            self.browser.sql.commit()

    def after(self):
        if not self.to_ban:
            return

        names = ', '.join([a for (a, b) in self.to_ban])
        reasons = '\n'.join(['#' + ': '.join(a) for a in self.to_ban])

        try:
            automod_config = self.browser.r.get_wiki_page(
                    self.browser.sub, 'config/automoderator')
        except Exception as e:
            print "Failed to load automod bans"
            print str(e)
            return

        new_content = unescape(automod_config.content_md)
        new_content = new_content.replace('#do_not_remove_a', reasons +
                                          '\n#do_not_remove_a')
        new_content = new_content.replace('do_not_remove_b',
                                          'do_not_remove_b, ' + names)

        try:
            self.browser.r.edit_wiki_page(self.browser.sub,
                                          'config/automoderator',
                                          new_content, "bans")
        except Exception as e:
            print "* Failed to update bans"
            print str(e)
            return
        else:
            print "Banned users"
            self.to_ban = []


class QuestionChecker(Checker):
    def __init__(self, browser):
        self.regex = re.compile("^(question|q)$", re.I)
        self.rule = "Question"
        self.note_text = (
                "Questions are best directed to /r/askphilosophy, "
                "which specializes in answers to philosophical questions!"
                )
        self.types = set([praw.objects.Submission])
        self.header = False
        self.footer = False
        Checker.__init__(self, browser)


class DevelopmentChecker(Checker):
    def __init__(self, browser):
        self.regex = re.compile("^(d|dev|develop)$", re.I)
        self.rule = "Underdeveloped"
        self.note_text = (
                "Posts on this subreddit need to not only have a "
                "philosophical subject matter, but must also present this "
                "subject matter in a developed manner. At a minimum, this "
                "includes: stating the problem being addressed; stating the "
                "thesis; stating how the thesis contributes to the problem; "
                "outlining some alternative answers to the same problem; "
                "something about why the stated thesis is preferable to the "
                "alternatives; anticipating some objections to the stated "
                "thesis and giving responses to them. These are just the "
                "minimum requirements."
                )
        self.types = set([praw.objects.Submission])
        self.header = False
        self.footer = True
        Checker.__init__(self, browser)

# TODO: Make reasons a proper instance attribute, maybe

class WarningChecker(Checker):
    def __init__(self, browser):
        self.regex = re.compile("^(w|warn)$", re.I)
        self.rule = "Comment Rule 1"
        self.types = set([praw.objects.Submission])
        self.note_text = (
                "I'd like to take a moment to remind everyone of our "
                "first commenting rule:\n\n>*Read the post before you "
                "reply.*\n\n>Read the posted content, understand and identify "
                "the philosophical arguments given, and respond to these "
                "substantively. If you have unrelated thoughts or don't wish "
                "to read the content, please post your own thread or simply "
                "refrain from commenting. Comments which are clearly not in "
                "direct response to the posted content may be removed.\n\n"
                "This sub is not in the business of one-liners, tangential "
                "anecdotes, or dank memes. Expect comment threads that break "
                "our rules to be removed."
                )
        Checker.__init__(self, browser)

    def action(self, post, mod):
        rule = self.rule
        note_text = self.note_text

        log_text = mod + " added comment rule warning on " + post.fullname + " by " + \
            str(post.author)
        print log_text
        self.browser.cur.execute('INSERT INTO actions (mod, action, reason) VALUES(?,?,?)',
                    (mod, "added comment warning on " + post.fullname + " by " +
                     str(post.author), rule))
        self.browser.sql.commit()

        # Build note text

        try:
            result = post.add_comment(note_text)
        except Exception as e:
            print "- Failed to add comment on " + post.fullname
            print str(e)
            return

        try:
            result.distinguish(sticky=True)
        except Exception as e:
            print "* Failed to distinguish comment on " + post.fullname
            print str(e)

class NukeChecker(Checker):
    def __init__(self, browser):
        self.regex = re.compile('^(n|nuke)( (?<rule>[0-9]+))$', re.I)
        self.types = set([praw.objects.Comment])
        Checker.__init__(self, browser)

    def action(self, post, mod, **kwargs):
        tree = praw.objects.Submission.from_url(self.browser.r, post.permalink)
        tree.replace_more_comments()
        comments = praw.helpers.flatten_tree(tree.comments)
        for comment in comments:
            comment.remove()

        if 'rule' in kwargs:
            rule = int(kwargs['rule'])
            if rule > len(self.browser.comment_rules):
                return

# TODO : warn user of rule violation


class RuleChecker(Checker):
    def __init__(self, browser):
        self.regex = re.compile(
                "^(RULE |(?P<radio>Posting Rule ))?(?P<rule>[0-9]+)"
                "(?(radio) - [\w ]*)$",
                re.I
                )
        self.types = set([praw.objects.Submission])
        self.header = True
        self.footer = True
        Checker.__init__(self, browser)

    def action(self, post, mod, **kwargs):
        rule = int(kwargs['rule'])
        if rule > len(self.browser.reasons):
            return

        Checker.action(self, post, mod, "Rule " + str(rule),
                       self.browser.reasons[rule - 1])


class SubredditBrowser:
    def __init__(self, sub_name, username, user_agent, checkers, sql, password=None):
        self.sql = sql
        self.cur = self.sql.cursor()
        self.cur.execute('CREATE TABLE IF NOT EXISTS actions(mod TEXT, action TEXT, reason '
                    'TEXT, time DATETIME DEFAULT CURRENT_TIMESTAMP)')
        self.cur.execute('CREATE TABLE IF NOT EXISTS notifications'
                    '(target TEXT, comment TEXT, reinstated INT DEFAULT 0)')
        print 'Loaded SQL database'
        self.sql.commit()
        self.sub_name = sub_name
        self.username = username
        self.user_agent = user_agent
        self.r = praw.Reddit(user_agent=user_agent)
        self.r.login(username, password=password, disable_warning=True)
        print "Logged in as " + username
        self.sub = self.r.get_subreddit(sub_name)

        our_foot = (
            "\n\n-----\n\nI am a bot. Please do not reply to this message, as "
            "it will likely go unread. Instead, use the link above to contact "
            "the moderators."
            )

        reasons_page = self.sub.get_wiki_page("toolbox")
        j = json.loads(reasons_page.content_md)
        self.header = urllib2.unquote(j['removalReasons']['header'])
        self.footer = urllib2.unquote(j['removalReasons']['footer']) + our_foot
        self.reasons = [urllib2.unquote(x['text'])
                        for x in j['removalReasons']['reasons']]
        print "Successfully loaded removal reasons"

        self.checkers = [checker(self) for checker in checkers]

    def scan_post(self, post):
        for mod_report in post.mod_reports:
            for checker in self.checkers:
                if post.__class__ not in checker.types:
                    return
                result = checker.check(mod_report[0])
                if type(result) == dict:
                    checker.action(post, mod_report[1], **result)
                    return

    def scan_reports(self):
        try:
            reports = self.sub.get_reports(limit=None)
            for post in reports:
                self.scan_post(post)
        except Exception as e:
            print "Error fetching reports: " + str(e)

        for checker in self.checkers:
            checker.after()

    def check_approvals(self):
        log = self.sub.get_mod_log(action='approvelink')
        try:
            for action in log:
                self.cur.execute('SELECT comment FROM notifications WHERE target = ? AND reinstated = ? LIMIT 1',
                        (action.target_fullname, False))
                row = self.cur.fetchone()
                if row:
                    try:
                        comment = self.r.get_info(thing_id=row[0])
                        comment.remove()
                        post = self.r.get_info(thing_id=action.target_fullname)
                        post.unlock()
                    except Exception as e:
                        print "Couldn't reinstate post: " + str(e)
                    else:
                        self.cur.execute('UPDATE notifications SET reinstated = ? WHERE target = ?',
                                (True, action.target_fullname))
                        self.sql.commit()
        except Exception as e:
            print "Couldn't get mod log: " + str(e)


if __name__ == '__main__':
    sub_name = "philosophy"
    username = "BernardJOrtcutt"
    user_agent = ("python:/r/Philosophy reporter:v1.0 "
                  "(by /u/TheGrammarBolshevik)")
    sql = sqlite3.connect('server/sql.db')

    our_browser = SubredditBrowser(sub_name, username, user_agent,
                                   [ShadowBanner,
                                    QuestionChecker,
                                    DevelopmentChecker,
                                    RuleChecker,
                                    WarningChecker],
                                   sql
                                   )

    while True:
        our_browser.scan_reports()
        our_browser.check_approvals()
        time.sleep(30)
