import actors
import helpers
import json
import logging
import praw
import re
import sqlite3
import time
import yaml


def build_regex(triggers):
    return re.compile("^(" + "|".join(re.escape(str(trigger))
                                      for trigger in triggers)
                      + ")$",
                      re.IGNORECASE)


class YAMLLoader:
    def __init__(self, db, cursor, subreddit):
        self.db = db
        self.cursor = cursor
        self.subreddit = subreddit

    def load(self, filename):
        with open(filename) as f:
            if filename.endswith('.yaml'):
                self.config = [x for x in yaml.safe_load_all(f)]
            return [self.parse_rule_config(rule_config)
                    for rule_config in self.config]

    def parse_subactor_config(self, subactor_configs):
        registry = actors.registry
        return [registry[subactor_config['type']](db=self.db,
                                                  cursor=self.cursor,
                                                  **subactor_config['params'])
                for subactor_config in subactor_configs]

    def parse_actor_config(self, actor_config):
        return actors.Actor(
            build_regex(actor_config['trigger']),
            [self._object_map(x) for x in actor_config['objects']],
            actor_config['remove'],
            self.parse_actor_config(actor_config['actions']),
            actor_config['name'],
            actor_config.get('details', default=''),
            self.db,
            self.cursor,
            self.subreddit
        )

    # TODO: please move or reorganize - should these registries be in one
    # place?
    #
    # We can create mapping functions for each sort of thing that is read out
    # of YAML - and ideally JSON as well
    def _object_map(self, obj):
        if obj == "post":
            return praw.objects.Submission
        if obj == "comment":
            return praw.objects.Comment


class SubredditRuleLoader:
    def __init__(self, db, cursor, subreddit):
        self.db = db
        self.cursor = cursor
        self.subreddit = subreddit

    def load(self):
        api_path = '/r/{}/about/rules/json'.format(self.subreddit.display_name)
        subrules = [rule
                    for rule in self.subreddit._reddit.get(api_path)['rules']
                    if rule['kind'] == 'link' or rule['kind'] == 'all']
        our_rules = []

        for i, subrule in enumerate(subrules, 1):
            note_text = "**{short_name}**\n\n{desc}".format(
                short_name=subrule['short_name'], desc=subrule['description'])
            our_rules.append(
                actors.Actor(build_regex(["RULE {n}".format(n=i),
                                          "{n}".format(n=i),
                                          subrule['short_name']]),
                             [praw.objects.Submission],
                             True,
                             [actors.Notifier(note_text=note_text,
                                              subreddit=self.subreddit,
                                              db=self.db)],
                             'removed',
                             'Rule {}'.format(i),
                             self.db,
                             self.cursor,
                             self.subreddit
                             )
            )

        return our_rules


# Idea: Have different "command source" classes to pull commands from
# reports, Slack, etc.
class Browser:
    def __init__(self, rules, subreddit):
        self.rules = rules
        self.subreddit = subreddit

    def check_command(self, command, mod, post):
        for rule in self.rules:
            rule.parse(command, mod, post)

    def scan_reports(self):
        try:
            for post in self.subreddit.get_reports(limit=None):
                for mod_report in post.mod_reports:
                    yield (mod_report[0], mod_report[1], post)
        except Exception as e:
            logging.error("Error fetching reports: {err}".format(err=e))

    def run(self):
        while True:
            try:
                for command in self.scan_reports():
                    self.check_command(*command)
                for rule in self.rules:
                    rule.after()
                time.sleep(30)
            except KeyboardInterrupt:
                print("Stopped by keyboard")
                break


def main():
    r = praw.Reddit('bjo test')
    r_philosophy = r.get_subreddit('philosophy')
    db = sqlite3.connect('new.db')
    cursor = db.cursor()
    loader = SubredditRuleLoader(db, cursor, r_philosophy)
    rules = loader.load()
    return rules

if __name__ == '__main__':
    # l = YAMLLoader(sqlite3.connect(':memory:'), 2)
    # a = l.load('config.yaml')
    main()
