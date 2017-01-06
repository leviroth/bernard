import actors
# import helpers
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
    def __init__(self, db, cursor, reddit):
        self.db = db
        self.cursor = cursor
        self.reddit = reddit

    def load(self, filename):
        # for moderator in self.subreddit.moderator:
        #     _, mod_id = helpers.deserialize_thing_id(moderator.fullname)
        #     cursor.execute('INSERT OR IGNORE INTO moderators (id, username) '
        #                    'VALUES(?,?)', (mod_id, str(moderator)))
        with open(filename) as f:
            if filename.endswith('.yaml'):
                config = yaml.safe_load(f)
        return [self.parse_subreddit_config(subreddit_config)
                for subreddit_config in config['subreddits']]

    def parse_subactor_config(self, subactor_configs, subreddit):
        registry = actors.registry
        return [registry[subactor_config['action']](
            db=self.db, cursor=self.cursor, subreddit=subreddit,
            **subactor_config['params'])
                for subactor_config in subactor_configs]

    def parse_actor_config(self, actor_config, subreddit):
        return actors.Actor(
            build_regex(actor_config['trigger']),
            [self._object_map(x) for x in actor_config['types']],
            actor_config['remove'],
            self.parse_subactor_config(actor_config['actions'], subreddit),
            actor_config['name'],
            actor_config.get('details'),
            self.db,
            self.cursor,
            subreddit
        )

    def parse_subreddit_config(self, subreddit_config):
        subreddit = self.reddit.subreddit(subreddit_config['name'])
        actors = [self.parse_actor_config(actor_config, subreddit)
                  for actor_config in subreddit_config['rules']]
        actors.extend(load_subreddit_rules(subreddit, self.db, self.cursor))
        return Browser(actors, subreddit, self.db, self.cursor)

    # TODO: please move or reorganize - should these registries be in one
    # place?
    #
    # We can create mapping functions for each sort of thing that is read out
    # of YAML - and ideally JSON as well
    def _object_map(self, obj):
        if obj == "post":
            return praw.models.Submission
        if obj == "comment":
            return praw.models.Comment


def load_subreddit_rules(subreddit, db, cursor):
    api_path = '/r/{}/about/rules.json'.format(subreddit.display_name)
    subrules = [rule
                for rule in subreddit._reddit.get(api_path)['rules']
                if rule['kind'] == 'link' or rule['kind'] == 'all']
    our_rules = []

    for i, subrule in enumerate(subrules, 1):
        note_text = "**{short_name}**\n\n{desc}".format(
            short_name=subrule['short_name'], desc=subrule['description'])
        command = build_regex(["RULE {n}".format(n=i), "{n}".format(n=i),
                               subrule['short_name']])
        actions = [actors.Notifier(text=note_text, subreddit=subreddit,
                                   db=db, cursor=cursor)]
        our_rules.append(
            actors.Actor(command, [praw.models.Submission], True, actions,
                         'removed', 'Rule {}'.format(i), db, cursor, subreddit)
        )

    return our_rules


# Idea: Have different "command source" classes to pull commands from
# reports, Slack, etc.
class Browser:
    def __init__(self, rules, subreddit, db, cursor):
        self.rules = rules
        self.subreddit = subreddit
        self.db = db
        self.cursor = cursor

    def check_command(self, command, mod, post):
        for rule in self.rules:
            rule.parse(command, mod, post)

    def scan_reports(self):
        try:
            for post in self.subreddit.mod.reports(limit=None):
                for mod_report in post.mod_reports:
                    yield (mod_report[0], mod_report[1], post)
        except Exception as e:
            logging.error("Error fetching reports: {err}".format(err=e))

    def run(self):
        while True:
            try:
                for command, mod, post in self.scan_reports():
                    self.check_command(command, mod, post)
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
