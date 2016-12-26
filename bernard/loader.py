import yaml
import re
import actors
import sqlite3
import praw
import logging
import time


def build_regex(triggers):
    return re.compile("^(" + "|".join(re.escape(str(trigger))
                                      for trigger in triggers)
                      + ")$",
                      re.IGNORECASE)


class YAMLLoader:
    def __init__(self, db, subreddit):
        self.db = db
        self.subreddit = subreddit

    def load(self, filename):
        with open(filename) as f:
            if filename.endswith('.yaml'):
                self.config = [x for x in yaml.safe_load_all(f)]
            return [self.parse_rule_config(rule_config)
                    for rule_config in self.config]

    def parse_actor_config(self, actor_configs):
        registry = actors.registry
        return [registry[actor_config['type']](db=self.db, subreddit=2,
                                               **actor_config['params'])
                for actor_config in actor_configs]

    def parse_rule_config(self, rule_config):
        return Rule(build_regex(rule_config['trigger']),
                    [self._object_map(x) for x in rule_config['objects']],
                    rule_config['remove'],
                    self.parse_actor_config(rule_config['actions'])
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
    def __init__(self, db, subreddit):
        self.db = db
        self.subreddit = subreddit

    def load(self):
        subrules = [rule for rule in self.subreddit.get_rules()['rules']
                    if rule['kind'] == 'link' or rule['kind'] == 'all']
        our_rules = []

        for i, subrule in enumerate(subrules, 1):
            note_text = "**{short_name}**\n\n{desc}".format(
                short_name=subrule['short_name'], desc=subrule['description'])
            our_rules.append(
                Rule(build_regex(["RULE {n}".format(n=i),
                                  "{n}".format(n=i),
                                  subrule['short_name']]),
                     [praw.objects.Submission],
                     True,
                     [actors.Notifier(note_text=note_text,
                                      subreddit=self.subreddit, db=self.db)]
                     ))

        return our_rules


class Rule:
    def __init__(self, trigger, targets, remove, actors, action_name,
                 action_details, db):
        self.trigger = trigger
        self.targets = targets
        self.remove = remove
        self.actors = actors
        self.action_name = action_name
        self.action_details = action_details
        self.db = db

    def match(self, command, post):
        return self.trigger.match(command) \
            and any(isinstance(post, target) for target in self.targets)

    def parse(self, command, post, mod):
        if self.match(command, post):
            for actor in self.actors:
                actor.action(post, mod)

            if self.remove:
                post.remove()
            else:
                post.approve()

            self.log_action(post, mod)

    def after(self):
        for actor in self.actors:
            actor.after()

    def deserialize_thing_id(thing_id):
        return tuple(int(x, base=36) for x in thing_id[1:].split('_'))

    def log_action(self, target, moderator):
        target_type, target_id = self.deserialize_thing_id(target.fullname)
        action_summary = self.action_name
        action_details = self.action_details
        _, author_id = self.deserialize_thing_id(target.author.fullname)
        self.cur.execute('INSERT IGNORE INTO users (id, username) '
                         'VALUES(?,?)', (author_id, target.author.fullname))
        self.cur.execute('SELECT id FROM moderators WHERE username=?',
                         moderator)
        moderator_id = self.cur.fetchone()[0]
        _, subreddit = self.deserialize_thing_id(self.subreddit.fullname)
        self.cur.execute(
            'INSERT INTO actions (target_type, target_id, action_summary, '
            'action_details, author, moderator, subreddit) '
            'VALUES(?,?,?,?,?,?,?)',
            (target_type, target_id, action_summary, action_details, author_id,
             moderator_id, subreddit)
        )
        self.db.commit()
        return self.cur.lastrowid


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

if __name__ == '__main__':
    # l = YAMLLoader(sqlite3.connect(':memory:'), 2)
    # a = l.load('config.yaml')
    r = praw.Reddit('bjo test')
    s = r.get_subreddit('philosophy')
    l = SubredditRuleLoader(sqlite3.connect(':memory:'), s)
    rules = l.load()
