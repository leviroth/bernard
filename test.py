import praw
import json
import urllib2
import re
import time
from xml.sax.saxutils import unescape

user_agent = "python:/r/Philosophy reporter:v0.2 (by /u/TheGrammarBolshevik)"
r = praw.Reddit(user_agent=user_agent)
r.login("BernardJOrtcutt")
print "Login successful"
our_sub = r.get_subreddit("philosophy")

print "Loaded"