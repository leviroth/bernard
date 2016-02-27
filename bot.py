import praw
import json
import urllib2
import re
import time
from xml.sax.saxutils import unescape

def scan_post(post):
    global to_ban

    p = re.compile("^(RULE |(?P<radio>Posting Rule ))?(?P<our_rule>[0-9]+)(?(radio) - [\w ]*)$", re.I)
    s = re.compile("^(shadowban|sb)$", re.I)
    q = re.compile("^(question|q)$", re.I)

    for mod_report in post.mod_reports:
        mis = s.match(mod_report[0])
        if mis:
            to_ban.append((str(post.author), post.permalink))

            print mod_report[1] + ' is shadowbanning ' + str(post.author)

            try:
                post.remove()
            except:
                print "- Failed to remove " + post.fullname
                return

        if isinstance(post, praw.objects.Submission):
            r_q = q.match(mod_report[0])

            if r_q:
                log_text = mod_report[1] + " removed " + post.fullname + \
                     " by " + str(post.author) + " [Question]"

                note_text = "Questions are best directed to /r/askphilosophy, which specializes in answers " + \
                     "to philosophical questions!"

                remove_post(post, log_text, note_text)

                return

            m = p.match(mod_report[0])

            if m:
                rule = int(m.group('our_rule'))
                if rule > len(reasons):
                    continue

                log_text = mod_report[1] + " removed " + post.fullname + \
                     " by " + str(post.author) + " [Rule " + str(rule) + "]"

                our_footer = footer.replace("{url}", urllib2.quote(post.permalink.encode('utf8')))
                note_text = header + "\n\n" + reasons[rule - 1] + "\n\n" + our_footer

                remove_post(post, log_text, note_text)

                return

def remove_post(post, log_text, note_text):
    try:
        post.remove()
    except:
        print "- Failed to remove " + post.fullname
        return

    print log_text

    try:
        result = post.add_comment(note_text)
    except:
        print "* Failed to add comment on " + post.fullname
        return

    try:
        result.distinguish()
    except:
        print "* Failed to distinguish comment on " + post.fullname

    return


def update_bans():
    global to_ban
    names = ', '.join([a for (a, b) in to_ban])
    reasons = '\n'.join(['#' + ': '.join(a) for a in to_ban])

    automod_config = r.get_wiki_page(our_sub, 'config/automoderator')
    new_content = unescape(automod_config.content_md)
    new_content = new_content.replace('#do_not_remove_a', reasons + '\n#do_not_remove_a')
    new_content = new_content.replace('do_not_remove_b', 'do_not_remove_b, ' + names)

    try:
        r.edit_wiki_page(our_sub, 'config/automoderator', new_content, "bans")
    except:
        print "* Failed to update bans"
    else:
        print "Banned users"
        to_ban = []


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
reasons = map(lambda x: urllib2.unquote(x['text']), j['removalReasons']['reasons'])

print "Successfully loaded removal reasons"

to_ban = []

while True:
    reports = our_sub.get_reports(limit=None)

    try:
        for post in reports:
            scan_post(post)
    except:
        print "- Error in fetching reports"
        time.sleep(5)
        continue

    if to_ban:
        update_bans()

    time.sleep(60)
