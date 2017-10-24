"""Module for loading configurations."""
import re

import praw
import yaml

from . import actors, browser, helpers

_TARGET_MAP = {
    "comment": praw.models.Comment,
    "post": praw.models.Submission,
}

_ACTOR_REGISTRY = {
    'ban': actors.Banner,
    'domainwatch': actors.AutomodDomainWatcher,
    'lock': actors.Locker,
    'notify': actors.Notifier,
    'nuke': actors.Nuker,
    'usernote': actors.ToolboxNoteAdder,
    'userwatch': actors.AutomodUserWatcher,
}


def build_regex(commands):
    """Turn commands iterable into a case-insensitive, 'inclusive-or' regex."""
    escaped_commands = (re.escape(str(command)) for command in commands)
    joined_commands = "|".join(escaped_commands)
    return re.compile("^(" + joined_commands + ")$", re.IGNORECASE)


def load_subreddit_rules(subreddit, rules, header, action_buffer_builder,
                         database):
    """Create a remover/notifier for each post rule."""
    post_rules = [
        rule for rule in rules
        if rule['kind'] == 'link' or rule['kind'] == 'all'
    ]
    our_rules = []

    for i, rule in enumerate(post_rules, 1):
        note_text = "**{short_name}**\n\n{desc}".format(
            short_name=rule['short_name'], desc=rule['description'])
        if header is not None:
            note_text = header + "\n\n" + note_text

        command = build_regex(
            ["RULE {n}".format(n=i), "{n}".format(n=i), rule['short_name']])
        actions = [
            actors.Notifier(
                text=note_text, subreddit=subreddit, database=database),
            actors.ToolboxNoteAdder(
                text="Post removed (Rule {})".format(i),
                level="abusewarn",
                buffer=action_buffer_builder.get(
                    actors.ToolboxNoteAdderActionBuffer),
                subreddit=subreddit,
                database=database)
        ]

        our_rules.append(
            actors.Rule(command, [praw.models.Submission], True, True, actions,
                        'Removed', 'Rule {}'.format(i), database, subreddit))

    return our_rules


def validate_actor_config(actor_class, params, target_types):
    """Raise exception if actor configuration is invalid."""
    if not set(target_types).issubset(actor_class.VALID_TARGETS):
        raise RuntimeError("{cls} does not support all of {targets}"
                           .format(cls=actor_class, targets=target_types))
    actor_class.validate_params(params)


def load_comment_rules(subreddit, rules, action_buffer_builder, database):
    """Create a nuker/warner for each comment rule."""
    header = "Please bear in mind our commenting rules:"
    comment_rules = [rule for rule in rules if rule['kind'] == 'comment']
    our_rules = []

    for i, rule in enumerate(comment_rules, 1):
        note_text = ">**{short_name}**\n\n>{desc}".format(
            short_name=rule['short_name'], desc=rule['description'])
        if header is not None:
            note_text = header + "\n\n" + note_text

        command = build_regex(["nuke {n}".format(n=i), "n {n}".format(n=i)])
        actions = [
            actors.Nuker(subreddit=subreddit, database=database),
            actors.Notifier(
                text=note_text, subreddit=subreddit, database=database),
            actors.ToolboxNoteAdder(
                text="Post removed (Rule {})".format(i),
                level="abusewarn",
                buffer=action_buffer_builder.get(
                    actors.ToolboxNoteAdderActionBuffer),
                subreddit=subreddit,
                database=database)
        ]

        our_rules.append(
            actors.Rule(command, [praw.models.Comment], True, False, actions,
                        'Nuked', 'Comment Rule {}'.format(i), database,
                        subreddit))

    return our_rules


class ActionBufferBuilder:
    """Provide ActionBuffers for a subreddit configuration."""

    def __init__(self, subreddit):
        """Initialize the ActionBufferBuilder class."""
        self.subreddit = subreddit
        self._buffers = {}

    def get(self, cls):
        """Return a shared ActionBuffer instance of the given class."""
        buffer = self._buffers.get(cls)
        if buffer is None:
            buffer = cls(self.subreddit)
            self._buffers[cls] = buffer
        return buffer

    @property
    def buffers(self):
        """Return a list of all buffer instances."""
        return list(self._buffers.values())


class YAMLLoader:
    """Loader for YAML files."""

    def __init__(self, database, reddit):
        """Initialize the YAMLLoader class."""
        self.database = database
        self.reddit = reddit

    def load(self, filename):
        """Parse the given file and return a list of Browsers."""
        with open(filename) as file:
            if filename.endswith('.yaml'):
                config = yaml.safe_load(file)
        return [
            self.parse_subreddit_config(subreddit_config)
            for subreddit_config in config['subreddits']
        ]

    def parse_rule_config(self, rule_config, subreddit, action_buffer_builder):
        """Return a Rule corresponding to rule_config."""
        command = build_regex(rule_config['trigger'])
        target_types = [_TARGET_MAP[x] for x in rule_config['types']]
        our_actors = [
            self.parse_actor_config(actor_config, subreddit,
                                    action_buffer_builder, target_types)
            for actor_config in rule_config.get('actions', [])
        ]

        return actors.Rule(command, target_types, rule_config['remove'],
                           rule_config.get('lock', rule_config['remove']),
                           our_actors, rule_config['name'],
                           rule_config.get('details'), self.database,
                           subreddit)

    def parse_actor_config(self, actor_config, subreddit,
                           action_buffer_builder, target_types):
        """Parse actor configuration and return a actor."""
        actor_class = _ACTOR_REGISTRY[actor_config['action']]
        params = actor_config.get('params', {})
        validate_actor_config(actor_class, params, target_types)
        if hasattr(actor_class, 'ACTION_BUFFER'):
            params['buffer'] = action_buffer_builder.get(
                actor_class.ACTION_BUFFER)
        return actor_class(
            database=self.database, subreddit=subreddit, **params)

    def parse_subreddit_config(self, subreddit_config):
        """Parse subreddit configuration and return a Browser."""
        subreddit = self.reddit.subreddit(subreddit_config['name'])
        action_buffer_builder = ActionBufferBuilder(subreddit)
        browser_rules = [
            self.parse_rule_config(rule_config, subreddit,
                                   action_buffer_builder)
            for rule_config in subreddit_config['rules']
        ]
        header = subreddit_config.get('header')
        sub_rules = subreddit.rules()['rules']
        # TODO

        # Add remover/notifier for subreddit rules and, if desired,
        # nuker/notifier for comment rules.
        if subreddit_config.get('default_post_actions'):
            browser_rules.extend(
                load_subreddit_rules(subreddit, sub_rules, header,
                                     action_buffer_builder, self.database))

        if subreddit_config.get('default_comment_actions'):
            browser_rules.extend(
                load_comment_rules(subreddit, sub_rules, action_buffer_builder,
                                   self.database))

        helpers.update_sr_tables(self.database.cursor(), subreddit)
        self.database.commit()

        return browser.Browser(browser_rules, action_buffer_builder.buffers,
                               subreddit, self.database)
