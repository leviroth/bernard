import praw
from .helper import BJOTest
from bernard import actors
from bernard.helpers import deserialize_thing_id


class TestRule(BJOTest):
    def setUp(self):
        super().setUp()
        notifier = actors.Notifier("A notifcation", self.subreddit)
        self.actor = actors.Rule(
            commands=["foo"],
            targets=[praw.models.Submission],
            remove=True,
            lock=True,
            actors=[notifier],
            action_name="Remove",
            action_details=None,
            database=self.db,
            subreddit=self.subreddit,
        )

    def test_match__correct_type(self):
        post = self.r.submission(id="5e7x7o")
        with self.recorder.use_cassette("TestRule.test_match__correct_type"):
            self.assertTrue(self.actor.match("foo", post))

    def test_match__incorrect_type(self):
        post = self.r.comment(id="dbnq46r")
        with self.recorder.use_cassette("TestRule.test_match__incorrect_type"):
            self.assertFalse(self.actor.match("foo", post))

    def test_parse(self):
        post = self.r.submission(id="5e7w80")
        post_fullname = "t3_5e7w80"
        post_type, post_id = deserialize_thing_id(post_fullname)
        self.assertFalse(self.actor._already_acted(post_fullname, "TGB"))
        with self.recorder.use_cassette("TestRule.test_parse"):
            self.actor.parse("foo", "TGB", post)
            post = self.r.submission(id="5e7w80")
            self.assertIsNotNone(post.banned_by)
            self.assertTrue(post.locked)
            self.cur.execute(
                "SELECT action_summary FROM actions "
                "WHERE target_type = 3 AND target_id = ?",
                (post_id,),
            )
            summary, *_ = self.cur.fetchone()
            self.assertTrue(self.actor._already_acted(post_fullname, "TGB"))
            self.assertFalse(self.actor._already_acted(post_fullname, "BJO"))
            self.assertEqual("Remove", summary)


class TestBanner(BJOTest):
    def test_action(self):
        actor = actors.Banner(
            "You banned", "testing purposes", 4, self.subreddit
        )
        post = self.r.submission(id="5e7wc7")
        with self.recorder.use_cassette("TestBanner.test_action"):
            actor.action(post, "TGB")
            self.assertIn(post.author, self.subreddit.banned())


class TestModmailer(BJOTest):
    def test_action(self):
        actor = actors.Modmailer("Test subject", "Test body", self.subreddit)
        post = self.r.submission(id="7fyr93")
        with self.recorder.use_cassette("TestModmailer.test_action"):
            actor.action(post, "BJO")


class TestNotifier(BJOTest):
    def test_action(self):
        actor = actors.Notifier("sample_text", self.subreddit)
        post = self.r.submission(id="5kgajm")
        with self.recorder.use_cassette("TestNotifier.test_action"):
            actor.action(post, "TGB")
            self.assertEqual(11, len(post.comments))

    def test_archived_target(self):
        actor = actors.Notifier("sample_text", self.subreddit)
        target = self.r.comment(id="djbaws1")
        with self.recorder.use_cassette("TestNotifier.test_archived_target"):
            actor.action(target, "BJO")

    def test_special_characters(self):
        actor = actors.Notifier("sample_text", self.subreddit)
        target = self.r.submission(id="8gz54v")
        with self.recorder.use_cassette(
            "TestNotifier.test_special_characters"
        ):
            actor.action(target, "BJO")


class TestNuker(BJOTest):
    def test_action(self):
        action_buffer = actors.NukerActionBuffer(self.subreddit)
        actor = actors.Nuker(action_buffer, self.subreddit)
        post = self.r.comment(id="dbnpgmz")
        with self.recorder.use_cassette("TestNuker.test_action"):
            actor.action(post, "TGB")
            child = self.r.comment(id="dbpa8kn")
            child.refresh()
            self.assertIsNotNone(child.banned_by)


class TestAutomodDomainWatcher(BJOTest):
    def test_action(self):
        buffer = actors.AutomodWatcherActionBuffer(self.subreddit)
        actor = actors.AutomodDomainWatcher(
            "test-placeholder", buffer, self.subreddit
        )
        post = self.r.submission(id="e9i3sl")
        with self.recorder.use_cassette(
            "TestAutomodDomainWatcher.test_action"
        ):
            actor.action(post, "TGB")
            placeholder_buffer = buffer.placeholder_dict["test-placeholder"]
            self.assertEqual(1, len(placeholder_buffer))

    def test_no_action_on_self_post(self):
        buffer = actors.AutomodWatcherActionBuffer(self.subreddit)
        actor = actors.AutomodDomainWatcher(
            "test-placeholder", buffer, self.subreddit
        )
        post = self.r.submission(id="e9ibcm")
        with self.recorder.use_cassette(
            "TestAutomodDomainWatcher.test_no_action_on_self_post"
        ):
            actor.action(post, "BJO")
            placeholder_buffer = buffer.placeholder_dict["test-placeholder"]
            self.assertEqual(0, len(placeholder_buffer))


class TestAutomodUserWatcher(BJOTest):
    def test_action(self):
        buffer = actors.AutomodWatcherActionBuffer(self.subreddit)
        actor = actors.AutomodUserWatcher(
            "test-placeholder", buffer, self.subreddit
        )
        post = self.r.comment(id="dbnpgmz")
        with self.recorder.use_cassette("TestAutomodUserWatcher.test_action"):
            actor.action(post, "TGB")
            placeholder_buffer = buffer.placeholder_dict["test-placeholder"]
            self.assertEqual(1, len(placeholder_buffer))
