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


def build_regex(commands):
    "Turn commands iterable into a case-insensitive, 'inclusive-or' regex."
    escaped_commands = (re.escape(str(command)) for command in commands)
    joined_commands = "|".join(escaped_commands)
    return re.compile("^(" + joined_commands + ")$",
                      re.IGNORECASE)


_target_map = {
    "comment": praw.models.Comment,
    "post":    praw.models.Submission,
}

_subactor_registry = {
    'ban':       actors.Banner,
    'notify':    actors.Notifier,
    'nuke':      actors.Nuker,
    'wikiwatch': actors.WikiWatcher
}

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

    def parse_subactor_config(self, subactor_config, subreddit):
        subactor_class = _subactor_registry[subactor_config['action']]
        return subactor_class(db=self.db, cursor=self.cursor,
                              subreddit=subreddit,
                              **subactor_config.get('params', {}))
        return [registry[subactor_config['action']](
            db=self.db, cursor=self.cursor, subreddit=subreddit,
            **subactor_config.get('params', {}))
                for subactor_config in subactor_configs]

    def parse_actor_config(self, actor_config, subreddit):
        "Return an Action corresponding to actor_config."
        command = build_regex(actor_config['trigger'])
        target_types = [_target_map[x] for x in actor_config['types']]
        subactors = [self.parse_subactor_config(subactor_config, subreddit)
                     for subactor_config in actor_config['actions']]

        return actors.Actor(
            command,
            target_types,
            actor_config['remove'],
            subactors,
            actor_config['name'],
            actor_config.get('details'),
            self.db,
            self.cursor,
            subreddit
        )

    def parse_subreddit_config(self, subreddit_config):
        """Return a Browser with actors draw from the configuration and the subreddit
        rules.

        """
        subreddit = self.reddit.subreddit(subreddit_config['name'])
        actors = [self.parse_actor_config(actor_config, subreddit)
                  for actor_config in subreddit_config['rules']]
        header = subreddit_config.get('header')
        sub_rules = get_rules(subreddit)

        # Add remover/notifier for subreddit rules and, if desired,
        # nuker/notifier for comment rules.
        actors.extend(
            load_subreddit_rules(subreddit, sub_rules, header, self.db,
                                 self.cursor))

        if subreddit_config.get('nuke_rules') is not None:
            actors.extend(
                load_comment_rules(subreddit, sub_rules, self.db, self.cursor))

        helpers.update_sr_tables(self.cursor, subreddit)
        self.db.commit()

        return browser.Browser(actors, subreddit, self.db, self.cursor)

def get_rules(subreddit):
    "Get subreddit's rules."
    api_path = '/r/{}/about/rules.json'.format(subreddit.display_name)
    return list(subreddit._reddit.get(api_path)['rules'])

def load_subreddit_rules(subreddit, rules, header, db, cursor):
    "Create a remover/notifier for each post rule."
    post_rules = [rule for rule in rules
                  if rule['kind'] == 'link' or rule['kind'] == 'all']
    our_rules = []

    for i, rule in enumerate(post_rules, 1):
        note_text = "**{short_name}**\n\n{desc}".format(
            short_name=rule['short_name'], desc=rule['description'])
        if header is not None:
            note_text = header + "\n\n" + note_text

        command = build_regex(["RULE {n}".format(n=i),
                               "{n}".format(n=i),
                               rule['short_name']])
        actions = [actors.Notifier(text=note_text, subreddit=subreddit,
                                   db=db, cursor=cursor)]
        our_rules.append(
            actors.Actor(command, [praw.models.Submission], True, actions,
                         'Removed', 'Rule {}'.format(i), db, cursor, subreddit)
        )

    return our_rules


def load_comment_rules(subreddit, rules, db, cursor):
    "Create a nuker/warner for each comment rule."
    header = "Please bear in mind our commenting rules:"
    api_path = '/r/{}/about/rules.json'.format(subreddit.display_name)
    comment_rules = [rule for rule in rules
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
