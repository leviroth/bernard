import unittest
from bernard import bot
from .helper import BJOTest
import praw
import json
import urllib2
import re
import time
import sqlite3
from xml.sax.saxutils import unescape

class CheckerTest(BJOTest):
    class OurChecker(bot.Checker):
        def __init__(self, browser):
            self.regex = re.compile("^X$", re.I)
            self.rule = "X"
            self.note_text = "Test removal reason"
            self.posts_only = True
            self.header = False
            self.footer = False
            bot.Checker.__init__(self, browser)

    def test_check(self):
        self.checker = self.OurChecker(self.browser)
        self.assertIsNotNone(self.checker.check('X'))
        self.assertIsNotNone(self.checker.check('x'))
        self.assertIsNone(self.checker.check('Y'))

    def test_action(self):
        self.checker = self.OurChecker(self.browser)
        self.r.login(self.un, password=self.un_pswd, disable_warning=True)
        post_id = self.r.submit(self.sr, 'CheckerTest.test_action', text='', send_replies=False).id
        post = self.browser.r.get_submission(submission_id=post_id)
        self.checker.action(post, 'TGB')

        time.sleep(10)
        post.refresh()
        self.assertIsNotNone(post.banned_by)
        self.assertTrue(post.locked)
        self.assertNotEqual(post.comments, [])

        comment = post.comments[0]
        self.assertEqual(str(comment), self.checker.note_text)
        self.assertTrue(comment.stickied)
        self.assertEqual(comment.distinguished, u'moderator')

class RuleCheckerTest(BJOTest):
    def test_check(self):
        self.checker = bot.RuleChecker(self.browser)
        self.assertIsNotNone(self.checker.check('1'))
        self.assertIsNotNone(self.checker.check('rule 2'))
        self.assertIsNotNone(self.checker.check('Posting Rule 3 - foo'))
        self.assertIsNone(self.checker.check('q'))

    def test_action(self):
        self.checker = bot.RuleChecker(self.browser)
        self.r.login(self.un, password=self.un_pswd, disable_warning=True)
        post_id = self.r.submit(self.sr, 'RuleCheckerTest.test_action', text='', send_replies=False).id
        post = self.browser.r.get_submission(submission_id=post_id)
        our_dict = self.checker.check('rule 1')
        self.checker.action(post, 'TGB', **our_dict)

        post.refresh()
        self.assertTrue(post.locked)

class QuestionCheckerTest(BJOTest):
    def test_check(self):
        self.checker = bot.QuestionChecker(self.browser)
        self.assertIsNotNone(self.checker.check('q'))
        self.assertIsNotNone(self.checker.check('question'))
        self.assertIsNone(self.checker.check('1'))

class DevelopmentCheckerTest(BJOTest):
    def test_check(self):
        self.checker = bot.DevelopmentChecker(self.browser)
        self.assertIsNotNone(self.checker.check('d'))
        self.assertIsNotNone(self.checker.check('dev'))
        self.assertIsNotNone(self.checker.check('develop'))
        self.assertIsNone(self.checker.check('1'))

class WarningCheckerTest(BJOTest):
    def test_check(self):
        self.checker = bot.WarningChecker(self.browser)
        self.assertIsNotNone(self.checker.check('w'))
        self.assertIsNotNone(self.checker.check('warn'))
        self.assertIsNone(self.checker.check('1'))

    def test_action(self):
        self.checker = bot.WarningChecker(self.browser)
        self.r.login(self.un, password=self.un_pswd, disable_warning=True)
        post_id = self.r.submit(self.sr, 'WarningCheckerTest.test_action', text='', send_replies=False).id
        post = self.browser.r.get_submission(submission_id=post_id)
        self.checker.action(post, 'TGB')

        post.refresh()
        self.assertTrue(post.comments[0].stickied)
        self.assertFalse(post.locked)

class ShadowBannerTest(BJOTest):
    def test_check(self):
        self.checker = bot.ShadowBanner(self.browser)
        self.assertIsNotNone(self.checker.check('sb'))
        self.assertIsNotNone(self.checker.check('shadowban'))
        self.assertIsNone(self.checker.check('foobar'))

    def test_action(self):
        self.checker = bot.ShadowBanner(self.browser)
        self.r.login(self.un, password=self.un_pswd, disable_warning=True)
        post_id = self.r.submit(self.sr, 'ShadowBannerTest.test_action', text='', send_replies=False).id
        post = self.browser.r.get_submission(submission_id=post_id)
        self.checker.action(post, 'TGB')

        post.refresh()
        self.assertIsNotNone(post.banned_by)
        self.assertEqual(self.checker.to_ban[0][0].lower(), self.un.lower())

    def test_after(self):
        self.checker = bot.ShadowBanner(self.browser)
        wiki_text = unescape(self.browser.r.get_wiki_page(
                self.browser.sub, 'config/automoderator').content_md)
        self.checker.to_ban = [(self.un, 'reddit.com')]
        self.checker.after()

        self.r.login(self.un, password=self.un_pswd, disable_warning=True)
        post_id = self.r.submit(self.sr, 'ShadowBannerTest.test_action', text='', send_replies=False).id
        post = self.browser.r.get_submission(submission_id=post_id)

        post.refresh()
        self.assertIsNotNone(post.banned_by)

        self.browser.r.edit_wiki_page(self.browser.sub, 'config/automoderator',
                wiki_text)

class NukeCheckerTest(BJOTest):
    def test_check(self):
        self.checker = bot.NukeChecker(self.browser)
        self.assertIsNotNone(self.checker.check('n'))
        self.assertIsNotNone(self.checker.check('nuke'))
        self.assertIsNone(self.checker.check('q'))

    def test_action(self):
        self.checker = bot.NukeChecker(self.browser)
        post = self.browser.r.get_submission(url='https://www.reddit.com/r/ThirdRealm/comments/4nj6vw/nuketesttest_action/d44bqfg')
        self.checker.action(post.comments[0], 'TGB')

        post.refresh()
        comments = praw.helpers.flatten_tree(post.comments)
        for comment in comments:
            self.assertTrue(comment.banned_by)
            comment.approve()
