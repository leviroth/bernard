import pytest

from bernard.loader import YAMLLoader

from .helper import BJOTest

pytestmark = pytest.mark.system


class SystemTest(BJOTest):
    def basic_test(self, test_name):
        loader = YAMLLoader(self.db, self.r)
        with self.recorder.use_cassette(
                'Test{}.system'.format(test_name)):
            browsers = loader.load(
                './test/configs/{}Config.yaml'.format(test_name))
            browsers[0].run()
        rows = self.db.execute('SELECT * FROM actions').fetchall()
        assert len(rows) == 1

    def test_automod_watcher(self):
        self.basic_test('AutomodWatcher')

    def test_banner(self):
        self.basic_test('Banner')

    def test_notifier(self):
        self.basic_test('Notifier')
        notification_count = self.db.execute(
            'SELECT COUNT() FROM notifications').fetchall()[0][0]
        assert notification_count == 1

    def test_nuker(self):
        self.basic_test('Nuker')

    def test_removal(self):
        self.basic_test('Removal')

    def test_usernote(self):
        self.basic_test('Usernote')