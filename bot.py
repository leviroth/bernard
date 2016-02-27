import praw
import json
import urllib2
import re
import time
from xml.sax.saxutils import unescape

def scan_post(post):
    global to_ban


    for mod_report in post.mod_reports:
        sb_check = re.compile("^(shadowban|sb)$", re.I)

        if sb_check.match(mod_report[0]):
            print mod_report[1] + ' is shadowbanning ' + str(post.author)

            try:
                post.remove()
            except Exception as e:
                print "- Failed to remove " + post.fullname
                print str(e)
            else:
                to_ban.append((str(post.author), post.permalink))
            return

        if isinstance(post, praw.objects.Submission):
            q_check = re.compile("^(question|q)$", re.I)

            if q_check.match(mod_report[0]):
                log_text = mod_report[1] + " removed " + post.fullname + \
                     " by " + str(post.author) + " [Question]"

                note_text = "Questions are best directed to /r/askphilosophy, which specializes in answers " + \
                     "to philosophical questions!"

                remove_post(post, log_text, note_text)

                return

            rule_check = re.compile("^(RULE |(?P<radio>Posting Rule ))?(?P<our_rule>[0-9]+)(?(radio) - [\w ]*)$", re.I)
            m = rule_check.match(mod_report[0])

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
    except Exception as e:
        print "- Failed to remove " + post.fullname
        print str(e)
        return

    print log_text

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
        result.distinguish()
    except Exception as e:
        print "* Failed to distinguish comment on " + post.fullname
        print str(e)

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
    except Exception as e:
        print "* Failed to update bans"
        print str(e)
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
reasons = [urllib2.unquote(x['text']) for x in j['removalReasons']['reasons']]

print "Successfully loaded removal reasons"

to_ban = []

while True:
    try:
        reports = our_sub.get_reports(limit=None)
    except Exception as e:
        print "Error fetching reports: " + str(e)
    else:
        for post in reports:
            scan_post(post)

    if to_ban:
        update_bans()

    time.sleep(30)
