import praw
import re
import unittest.mock
from .helper import BJOTest
from bernard import browser, actors


class TestBrowser(BJOTest):
    def setUp(self):
        super().setUp()
        self.subactor = unittest.mock.MagicMock()
        self.actor = actors.Actor(
            trigger=re.compile('foo', re.I),
            targets=[praw.models.Submission],
            remove=False,
            subactors=[self.subactor],
            action_name="Remove",
            action_details=None,
            database=self.db,
            subreddit=self.subreddit)
        self.browser = browser.Browser([self.actor], [], self.subreddit,
                                       self.db)

    def test_run(self):
        with self.recorder.use_cassette('TestBrowser.test_run'):
            self.browser.run()
            self.assertTrue(self.subactor.action.called)

    def test_empty_string_report(self):
        with self.recorder.use_cassette(
                'TestBrowser.test_empty_string_report'):
            self.browser.run()
