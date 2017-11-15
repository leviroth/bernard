import praw
import unittest.mock
from .helper import BJOTest
from bernard import browser, actors


class TestBrowser(BJOTest):
    def setUp(self):
        super().setUp()
        self.actor = unittest.mock.MagicMock()
        self.rule = actors.Rule(
            commands=['foo'],
            targets=[praw.models.Submission],
            remove=False,
            lock=False,
            actors=[self.actor],
            action_name="Remove",
            action_details=None,
            database=self.db,
            subreddit=self.subreddit)
        self.browser = browser.Browser([self.rule], [], self.subreddit,
                                       self.db)

    def test_run(self):
        with self.recorder.use_cassette('TestBrowser.test_run'):
            self.browser.run()
            self.assertTrue(self.actor.action.called)

    def test_empty_string_report(self):
        with self.recorder.use_cassette(
                'TestBrowser.test_empty_string_report'):
            self.browser.run()
