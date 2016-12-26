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
