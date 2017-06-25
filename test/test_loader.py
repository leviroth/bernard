from .helper import BJOTest
from bernard.actors import Locker, Notifier
from bernard.loader import YAMLLoader, validate_actor_config
from praw.models import Comment, Submission


class TestValidation(BJOTest):
    def setUp(self):
        super().setUp()
        self.loader = YAMLLoader(self.db, self.subreddit)

    def test_bad_param_type(self):
        params = {'text': 3}
        with self.assertRaises(RuntimeError):
            validate_actor_config(Notifier, params, [])

    def test_good_param_type(self):
        params = {'text': "foobar"}
        validate_actor_config(Notifier, params, [])

    def test_bad_target_type(self):
        with self.assertRaises(RuntimeError):
            validate_actor_config(Locker, {}, [Comment])

    def test_good_target_type(self):
        validate_actor_config(Locker, {}, [Submission])
