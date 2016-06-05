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
        if self.regex.match(report):
            return {}

    # TODO: Looks like we can't use self for the defaults
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
        self.posts_only = False
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
        self.posts_only = True
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
        self.posts_only = True
        self.header = False
        self.footer = True
        Checker.__init__(self, browser)

# TODO: Make reasons a proper instance attribute, maybe


class RuleChecker(Checker):
    def __init__(self, browser):
        self.regex = re.compile(
                "^(RULE |(?P<radio>Posting Rule ))?(?P<our_rule>[0-9]+)"
                "(?(radio) - [\w ]*)$",
                re.I
                )
        self.posts_only = True
        self.header = True
        self.footer = True
        Checker.__init__(self, browser)

    def check(self, report):
        m = self.regex.match(report)

        if m:
            rule = int(m.group('our_rule'))
            if rule > len(self.browser.reasons):
                return None

            return {"rule": rule}

    def action(self, post, mod, **kwargs):
        rule = kwargs['rule']
        Checker.action(self, post, mod, "Rule " + str(rule),
                       self.browser.reasons[rule - 1])


class SubredditBrowser:
    def __init__(self, sub_name, username, user_agent, checkers, db_file):
        self.sql = sqlite3.connect(db_file)
        self.cur = self.sql.cursor()
        self.cur.execute('CREATE TABLE IF NOT EXISTS actions(mod TEXT, action TEXT, reason '
                    'TEXT, time DATETIME DEFAULT CURRENT_TIMESTAMP)')
        print 'Loaded SQL database'
        self.sql.commit()
        self.sub_name = sub_name
        self.username = username
        self.user_agent = user_agent
        self.r = praw.Reddit(user_agent=user_agent)
        self.r.login(username, disable_warning=True)
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
                if checker.posts_only \
                        and not isinstance(post, praw.objects.Submission):
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


if __name__ == '__main__':
    sub_name = "philosophy"
    username = "BernardJOrtcutt"
    user_agent = ("python:/r/Philosophy reporter:v1.0 "
                  "(by /u/TheGrammarBolshevik)")
    db_file = 'server/sql.db'

    our_browser = SubredditBrowser(sub_name, username, user_agent,
                                   [ShadowBanner,
                                    QuestionChecker,
                                    DevelopmentChecker,
                                    RuleChecker],
                                   db_file
                                   )

    while True:
        our_browser.scan_reports()
        time.sleep(30)
