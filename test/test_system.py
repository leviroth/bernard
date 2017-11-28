from contextlib import redirect_stderr
from io import StringIO
import pytest

from bernard.actors import (AutomodDomainWatcher, AutomodUserWatcher, Banner,
                            Notifier, Nuker, ToolboxNoteAdder)
from bernard.loader import load_yaml_config

from .helper import BJOTest

pytestmark = pytest.mark.system


class SystemTest(BJOTest):
    def basic_test(self, test_name):
        with self.recorder.use_cassette('Test{}.system'.format(test_name)):
            browser = load_yaml_config(
                self.db, self.subreddit,
                './test/configs/{}Config.yaml'.format(test_name))
            temp_stderr = StringIO()
            with redirect_stderr(temp_stderr):
                browser.run()
            assert temp_stderr.getvalue() == ""
            assert all(
                interaction.used
                for interaction in self.recorder.current_cassette.interactions)
        rows = self.db.execute('SELECT * FROM actions').fetchall()
        assert len(rows) == 1
        return browser

    def test_automod_domain_watcher(self):
        browser = self.basic_test('AutomodDomainWatcher')
        assert any(
            isinstance(actor, AutomodDomainWatcher)
            for actor in browser.rules[0].actors)

    def test_automod_hybrid_watcher(self):
        browser = self.basic_test('AutomodHybridWatcher')
        assert any(
            isinstance(actor, AutomodDomainWatcher)
            for actor in browser.rules[0].actors)
        assert any(
            isinstance(actor, AutomodUserWatcher)
            for actor in browser.rules[0].actors)

    def test_automod_user_watcher(self):
        browser = self.basic_test('AutomodUserWatcher')
        assert any(
            isinstance(actor, AutomodUserWatcher)
            for actor in browser.rules[0].actors)

    def test_banner(self):
        browser = self.basic_test('Banner')
        assert any(
            isinstance(actor, Banner) for actor in browser.rules[0].actors)

    def test_notifier(self):
        browser = self.basic_test('Notifier')
        assert any(
            isinstance(actor, Notifier) for actor in browser.rules[0].actors)

    def test_nuker(self):
        browser = self.basic_test('Nuker')
        assert any(
            isinstance(actor, Nuker) for actor in browser.rules[0].actors)

    def test_removal(self):
        browser = self.basic_test('Removal')
        assert browser.rules[0].remove

    def test_usernote(self):
        browser = self.basic_test('Usernote')
        assert any(
            isinstance(actor, ToolboxNoteAdder)
            for actor in browser.rules[0].actors)
