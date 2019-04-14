"""Module for loading configurations."""
import praw
import yaml

from . import actors, browser, helpers

_TARGET_MAP = {"comment": praw.models.Comment, "post": praw.models.Submission}

_ACTOR_REGISTRY = {
    "ban": actors.Banner,
    "domainwatch": actors.AutomodDomainWatcher,
    "lock": actors.Locker,
    "modmail": actors.Modmailer,
    "notify": actors.Notifier,
    "nuke": actors.Nuker,
    "usernote": actors.ToolboxNoteAdder,
    "userwatch": actors.AutomodUserWatcher,
}


def validate_actor_config(actor_class, params, target_types):
    """Raise exception if actor configuration is invalid."""
    if not set(target_types).issubset(actor_class.VALID_TARGETS):
        raise RuntimeError(
            "{cls} does not support all of {targets}".format(
                cls=actor_class, targets=target_types
            )
        )
    actor_class.validate_params(params)


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


class _ActionConfig:
    def __init__(self, data):
        if isinstance(data, str):
            self.action = data
            self.params = {}
        elif isinstance(data, dict):
            self.action, self.params = next(iter(data.items()))


def parse_actor_config(subreddit, action_buffer_builder, config, target_types):
    """Parse actor configuration and return a actor."""
    actor_class = _ACTOR_REGISTRY[config.action]
    params = config.params
    validate_actor_config(actor_class, params, target_types)
    if hasattr(actor_class, "ACTION_BUFFER"):
        params["action_buffer"] = action_buffer_builder.get(
            actor_class.ACTION_BUFFER
        )
    return actor_class(subreddit=subreddit, **params)


def parse_subreddit_config(database, subreddit, config):
    """Parse subreddit configuration and return a Browser."""
    action_buffer_builder = ActionBufferBuilder(subreddit)
    browser_rules = [
        parse_rule_config(
            database, subreddit, action_buffer_builder, rule_config
        )
        for rule_config in config
    ]

    helpers.update_sr_tables(database.cursor(), subreddit)
    database.commit()

    return browser.Browser(
        browser_rules, action_buffer_builder.buffers, subreddit, database
    )


def load_yaml_config(database, subreddit, config_file):
    """Parse the given file and return a list of Browsers."""
    with config_file.open() as file:
        config = yaml.safe_load_all(file)
        return parse_subreddit_config(database, subreddit, config)


def parse_rule_config(database, subreddit, action_buffer_builder, rule_config):
    """Return a Rule corresponding to rule_config."""
    target_types = [_TARGET_MAP[x] for x in rule_config["trigger"]["types"]]
    action_configs = [_ActionConfig(x) for x in rule_config.get("actions", [])]

    new_action_configs = []
    remove = lock = False
    for action_config in action_configs:
        if action_config.action == "remove":
            remove = True
            lock = (
                action_config.params.get("lock", True)
                and praw.models.Submission in target_types
            )
        else:
            new_action_configs.append(action_config)
    our_actors = [
        parse_actor_config(
            subreddit, action_buffer_builder, actor_config, target_types
        )
        for actor_config in new_action_configs
    ]

    return actors.Rule(
        commands=[
            command.casefold()
            for command in rule_config["trigger"]["commands"]
        ],
        targets=target_types,
        remove=remove,
        lock=lock,
        actors=our_actors,
        action_name=rule_config["info"]["name"],
        action_details=rule_config["info"].get("details"),
        database=database,
        subreddit=subreddit,
    )
