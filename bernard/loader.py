import actors
import browser
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
    def __init__(self, db, cursor, reddit):
        self.db = db
        self.cursor = cursor
        self.reddit = reddit

    def load(self, filename):
        with open(filename) as f:
            if filename.endswith('.yaml'):
                config = yaml.safe_load(f)
        return [self.parse_subreddit_config(subreddit_config)
                for subreddit_config in config['subreddits']]

    def parse_subactor_config(self, subactor_configs, subreddit):
        registry = actors.registry
        return [registry[subactor_config['action']](
            db=self.db, cursor=self.cursor, subreddit=subreddit,
            **subactor_config.get('params', {}))
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
        header = subreddit_config.get('header')
        actors.extend(load_subreddit_rules(subreddit, header, self.db,
                                           self.cursor))
        if subreddit_config.get('nuke_rules') is not None:
            actors.extend(load_comment_rules(subreddit, self.db, self.cursor))

        helpers.update_sr_tables(self.cursor, subreddit)
        self.db.commit()

        return browser.Browser(actors, subreddit, self.db, self.cursor)

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


def load_subreddit_rules(subreddit, header, db, cursor):
    api_path = '/r/{}/about/rules.json'.format(subreddit.display_name)
    subrules = [rule
                for rule in subreddit._reddit.get(api_path)['rules']
                if rule['kind'] == 'link' or rule['kind'] == 'all']
    our_rules = []

    for i, subrule in enumerate(subrules, 1):
        note_text = "**{short_name}**\n\n{desc}".format(
            short_name=subrule['short_name'], desc=subrule['description'])
        if header is not None:
            note_text = header + "\n\n" + note_text

        command = build_regex(["RULE {n}".format(n=i), "{n}".format(n=i),
                               subrule['short_name']])
        actions = [actors.Notifier(text=note_text, subreddit=subreddit,
                                   db=db, cursor=cursor)]
        our_rules.append(
            actors.Actor(command, [praw.models.Submission], True, actions,
                         'Removed', 'Rule {}'.format(i), db, cursor, subreddit)
        )

    return our_rules


def load_comment_rules(subreddit, db, cursor):
    header = "Please bear in mind our commenting rules:"
    api_path = '/r/{}/about/rules.json'.format(subreddit.display_name)
    comment_rules = [rule
                    for rule in subreddit._reddit.get(api_path)['rules']
                    if rule['kind'] == 'comment']
    our_rules = []

    for i, rule in enumerate(comment_rules, 1):
        note_text = ">**{short_name}**\n\n>{desc}".format(
            short_name=rule['short_name'], desc=rule['description'])
        if header is not None:
            note_text = header + "\n\n" + note_text

        command = build_regex(["nuke {n}".format(n=i), "n {n}".format(n=i)])
        actions = [actors.Nuker(subreddit=subreddit, db=db, cursor=cursor),
                   actors.Notifier(text=note_text, subreddit=subreddit,
                                   db=db, cursor=cursor)]
        our_rules.append(
            actors.Actor(command, [praw.models.Comment], True, actions,
                         'Nuked', 'Comment Rule {}'.format(i), db, cursor, subreddit)
        )

    return our_rules


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
