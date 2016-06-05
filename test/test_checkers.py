import unittest
from bernard import bot
from .helper import BJOTest

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
        self.checker.action(post, 'TGB', **{'rule': 1})

        post.refresh()
        self.assertTrue(post.locked)
