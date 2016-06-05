import unittest
from bernard import bot
from praw import Reddit
import sqlite3

USER_AGENT = 'BJO_test_suite'

class BJOTest(unittest.TestCase):
    def configure(self):
        self.r = Reddit('BJO_test_suite_friend', disable_update_check=True)
        self.user_agent = USER_AGENT
        self.sr = 'thirdrealm'
        self.un = 'BJO_test_user'
        self.mod_un = 'BJO_test_mod'
        self.un_pswd = '123456'
        self.mod_un_pswd = '123456'

    def setUp(self):
        self.configure()
        sql = sqlite3.connect(':memory:')
        self.browser = bot.SubredditBrowser(self.sr, self.mod_un, self.user_agent,
                [bot.ShadowBanner,
                 bot.QuestionChecker,
                 bot.DevelopmentChecker,
                 bot.RuleChecker],
                sql, password='123456')
