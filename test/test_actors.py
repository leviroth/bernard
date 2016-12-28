from .helper import BJOTest
from bernard import actors


class TestNotifier(BJOTest):
    def test_action(self):
        actor = actors.Notifier("sample_text", self.db, self.cur,
                                self.subreddit)
        post = self.r.submission(id='5kgajm')
        with self.recorder.use_cassette('TestNotifier.test_action'):
            actor.action(post, 'TGB')
            self.assertEqual(11, len(post.comments))


class TestBanner(BJOTest):
    def test_action(self):
        actor = actors.Banner("You banned", "testing purposes", 4,
                              self.db, self.cur, self.subreddit)
        post = self.r.submission(id='5e7wc7')
        with self.recorder.use_cassette('TestBanner.test_action'):
            actor.action(post, 'TGB')
            self.assertIn(post.author, self.subreddit.banned())


class TestNuker(BJOTest):
    def test_action(self):
        actor = actors.Nuker(self.db, self.cur, self.subreddit)
        post = self.r.comment(id='dbnpgmz')
        with self.recorder.use_cassette('TestNuker.test_action'):
            actor.action(post, 'TGB')
            child = self.r.comment(id='dbpa8kn')
            child.refresh()
            self.assertIsNotNone(child.banned_by)
