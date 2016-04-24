import praw
import json
import urllib2
import re
import time
import sqlite3
from xml.sax.saxutils import unescape

sql = sqlite3.connect('server/sql.db')
cur = sql.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS actions(mod TEXT, action TEXT, reason TEXT,' + \
        ' time DATETIME DEFAULT CURRENT_TIMESTAMP)')
print 'Loaded SQL database'
sql.commit()

# TODO: Need to figure out how logging will work

class Checker:
    def __init__(self, footed=False):
        self.footed = footed

    def check(self, report):
        if self.regex.match(report):
            return {}

    def action(self, post, mod, rule=self.rule, note_text=self.note_text):
        try:
            post.remove()
        except Exception as e:
            print "- Failed to remove " + post.fullname
            print str(e)
            return

        log_text = mod + " removed " + post.fullname + " by " + \
                str(post.author) + " [" + rule + "]"
        print log_text
        cur.execute('INSERT INTO actions (mod, action, reason) VALUES(?,?,?)',
                (mod, "removed " + post.fullname + \ " by " + str(post.author),
                    rule))
        sql.commit()

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
    def __init__(self):
        self.to_ban = []
        self.regex = re.compile("^(shadowban|sb)$", re.I)

    def action(self, post, mod):
        try:
            post.remove()
        except Exception as e:
            print "- Failed to remove " + post.fullname
            print str(e)
        else:
            self.to_ban.append((str(post.author), post.permalink))

            #cur.execute('INSERT INTO actions (mod, action, reason) VALUES(?,?,?)', (mod_report[1],
            #        'banned ' + str(post.author), post.permalink))
            #sql.commit()

    def after(self):
        if not self.to_ban:
            return

        names = ', '.join([a for (a, b) in self.to_ban])
        reasons = '\n'.join(['#' + ': '.join(a) for a in self.to_ban])

        try:
            automod_config = r.get_wiki_page(our_sub, 'config/automoderator')
        except Exception as e:
            print "Failed to load automod bans"
            print str(e)
            return

        new_content = unescape(automod_config.content_md)
        new_content = new_content.replace('#do_not_remove_a', reasons + \
                '\n#do_not_remove_a')
        new_content = new_content.replace('do_not_remove_b',
                'do_not_remove_b, ' + names)

        try:
            r.edit_wiki_page(our_sub, 'config/automoderator', new_content,
                    "bans")
        except Exception as e:
            print "* Failed to update bans"
            print str(e)
            return
        else:
            print "Banned users"
            self.to_ban = []

class QuestionChecker(Checker):
    def __init__(self):
        self.regex = re.compile("^(question|q)$", re.I)
        self.rule = "Question"
        self.note_text = ("Questions are best directed to /r/askphilosophy, "
                "which specializes in answers to philosophical questions!")

class DevelopmentChecker(Checker):
    def __init__(self):
        self.regex = re.compile("^(d|dev|develop)$", re.I)
        self.rule = "Underdeveloped"
        self.note_text = ("Posts on this subreddit need to not only have a "
                "philosophical subject matter, but must also present this "
                "subject matter in a developed manner. At a minimum, this "
                "includes: stating the problem being addressed; stating the "
                "thesis; stating how the thesis contributes to the problem; "
                "outlining some alternative answers to the same problem; "
                "something about why the stated thesis is preferable to the "
                "alternatives; anticipating some objections to the stated "
                "thesis and giving responses to them. These are just the "
                "minimum requirements.")
        super(Checker, self).__init__(True)

# TODO: Make reasons a proper instance attribute

class RuleChecker(Checker):
    def __init__(self):
        self.regex = re.compile("^(RULE |(?P<radio>Posting Rule ))?"
                "(?P<our_rule>[0-9]+)(?(radio) - [\w ]*)$", re.I)
        super(Checker, self).__init__(True)

    def check(self, report):
        m = self.regex.match(report)

        if m:
            rule = int(m.group('our_rule'))
            if rule > len(reasons):
                return None

            return {"rule": rule}

def scan_post(post):
    for mod_report in post.mod_reports:



#our_footer = footer.replace("{url}", urllib2.quote(post.permalink.encode('utf8')))

# Set up, log in, etc.

sub_name = "philosophy"
username = "BernardJOrtcutt"

user_agent = "python:/r/Philosophy reporter:v0.3 (by /u/TheGrammarBolshevik)"
r = praw.Reddit(user_agent=user_agent)
r.login(username, disable_warning=True)
print "Logged in as " + username
our_sub = r.get_subreddit(sub_name)
print "Our subreddit: " + sub_name

# Load removal reasons from the toolbox wiki page

our_foot = """

-----

I am a bot. Please do not reply to this message, as it will likely go unread. Instead, use the link above to contact the moderators.
"""

reasons_page = our_sub.get_wiki_page("toolbox")
j = json.loads(reasons_page.content_md)
header = urllib2.unquote(j['removalReasons']['header'])
footer = urllib2.unquote(j['removalReasons']['footer']) + our_foot
reasons = [urllib2.unquote(x['text']) for x in j['removalReasons']['reasons']]

print "Successfully loaded removal reasons"

to_ban = []

while True:
    try:
        reports = our_sub.get_reports(limit=None)
        for post in reports:
            scan_post(post)
    except Exception as e:
        print "Error fetching reports: " + str(e)

    if to_ban:
        update_bans()

    time.sleep(30)
