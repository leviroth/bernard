from .helper import BJOTest
from bernard import actors
from mock import patch


class TestBanner(BJOTest):
    @patch('time.sleep', return_value=None)
    def test_action(self, _):
        actor = actors.Banner("You banned", "testing purposes", 4,
                              self.db, self.cur, self.subreddit)
        post = self.r.submission(id='5e7wc7')
        with self.recorder.use_cassette('TestBanner.test_action'):
            actor.action(post, 'TGB')
            self.assertIn(post.author, self.subreddit.banned())


class TestNotifier(BJOTest):
    @patch('time.sleep', return_value=None)
    def test_action(self, _):
        actor = actors.Notifier("sample_text", self.db, self.cur,
                                self.subreddit)
        post = self.r.submission(id='5kgajm')
        with self.recorder.use_cassette('TestNotifier.test_action'):
            actor.action(post, 'TGB')
            self.assertEqual(11, len(post.comments))


class TestNuker(BJOTest):
    @patch('time.sleep', return_value=None)
    def test_action(self, _):
        actor = actors.Nuker(self.db, self.cur, self.subreddit)
        post = self.r.comment(id='dbnpgmz')
        with self.recorder.use_cassette('TestNuker.test_action'):
            actor.action(post, 'TGB')
            child = self.r.comment(id='dbpa8kn')
            child.refresh()
            self.assertIsNotNone(child.banned_by)


class TestWikiWatcher(BJOTest):
    def test_action(self):
        actor = actors.WikiWatcher('test-placeholder', self.db, self.cur,
                                   self.subreddit)
        post = self.r.comment(id='dbnpgmz')
        with self.recorder.use_cassette('TestWikiWatcher.test_action'):
            actor.action(post, 'TGB')
            self.assertEqual(1, len(actor.to_add))
            self.assertEqual('BJO_test_mod', actor.to_add[0])

    @patch('time.sleep', return_value=None)
    def test_after(self, _):
        actor = actors.WikiWatcher('test!placeholder', self.db, self.cur,
                                   self.subreddit)
        actor.to_add.append('BJO_test_mod')
        with self.recorder.use_cassette('TestWikiWatcher.test_after'):
            actor.after()
            automod_config = self.subreddit.wiki['config/automoderator']
            first_line = automod_config.content_md.splitlines()[0].strip()
            self.assertEqual('author: [test!placeholder, BJO_test_mod,]',
                             first_line)
