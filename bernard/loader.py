import yaml
import re
import actors
import sqlite3
import praw


class Loader:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')

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
        return Rule(rule_config['trigger'],
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


class Rule:
    def __init__(self, triggers, targets, remove, actors):
        self.trigger = re.compile(
            "^(" + '|'.join(re.escape(trigger) for trigger in triggers) + ")$",
            re.IGNORECASE
        )
        self.targets = targets
        self.remove = remove
        self.actors = actors

    def parse(self, command, post, mod):
        if (re.match(command)):
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

if __name__ == '__main__':
    l = Loader()
    a = l.load('config.yaml')
