import praw
import re
from .helper import BJOTest
from bernard import actors


class TestRule(BJOTest):
    def setUp(self):
        super().setUp()
        notifier = actors.Notifier('A notifcation', self.db, self.subreddit)
        self.actor = actors.Rule(
            trigger=re.compile('foo', re.I),
            targets=[praw.models.Submission],
            remove=True,
            actors=[notifier],
            action_name="Remove",
            action_details=None,
            database=self.db,
            subreddit=self.subreddit)

    def test_match__correct_type(self):
        post = self.r.submission(id='5e7x7o')
        with self.recorder.use_cassette('TestRule.test_match__correct_type'):
            self.assertTrue(self.actor.match('foo', post))

    def test_match__incorrect_type(self):
        post = self.r.comment(id='dbnq46r')
        with self.recorder.use_cassette(
                'TestRule.test_match__incorrect_type'):
            self.assertFalse(self.actor.match('foo', post))

    def test_parse(self):
        post = self.r.submission(id='5e7w80')
        with self.recorder.use_cassette('TestRule.test_parse'):
            self.actor.parse('foo', 'TGB', post)
            post = self.r.submission(id='5e7w80')
            self.assertIsNotNone(post.banned_by)
            self.assertTrue(post.locked)
            post_id = int('5e7w80', base=36)
            self.cur.execute('SELECT action_summary, id FROM actions '
                             'WHERE target_type = 3 AND target_id = ?',
                             (post_id, ))
            summary, action_id = self.cur.fetchone()
            self.assertEqual('Remove', summary)
            self.cur.execute('SELECT * FROM removals WHERE action_id = ?',
                             (action_id, ))


class TestBanner(BJOTest):
    def test_action(self):
        actor = actors.Banner("You banned", "testing purposes", 4, self.db,
                              self.subreddit)
        post = self.r.submission(id='5e7wc7')
        with self.recorder.use_cassette('TestBanner.test_action'):
            actor.action(post, 'TGB', action_id=1)
            self.assertIn(post.author, self.subreddit.banned())


class TestNotifier(BJOTest):
    def test_action(self):
        actor = actors.Notifier("sample_text", self.db, self.subreddit)
        post = self.r.submission(id='5kgajm')
        with self.recorder.use_cassette('TestNotifier.test_action'):
            actor.action(post, 'TGB', action_id=1)
            self.assertEqual(11, len(post.comments))
            self.cur.execute('SELECT * FROM notifications WHERE action_id = 1')
            self.assertIsNotNone(self.cur.fetchone())


class TestNuker(BJOTest):
    def test_action(self):
        actor = actors.Nuker(self.db, self.subreddit)
        post = self.r.comment(id='dbnpgmz')
        with self.recorder.use_cassette('TestNuker.test_action'):
            actor.action(post, 'TGB', action_id=1)
            child = self.r.comment(id='dbpa8kn')
            child.refresh()
            self.assertIsNotNone(child.banned_by)


class TestAutomodWatcher(BJOTest):
    def test_action(self):
        buffer = actors.AutomodWatcherActionBuffer(self.subreddit)
        actor = actors.AutomodWatcher('test-placeholder', buffer, self.db,
                                      self.subreddit)
        post = self.r.comment(id='dbnpgmz')
        with self.recorder.use_cassette('TestAutomodWatcher.test_action'):
            actor.action(post, 'TGB', action_id=1)
            placeholder_buffer = buffer.placeholder_dict['test-placeholder']
            self.assertEqual(1,
                             len(placeholder_buffer))
