## Synopsis ##

Bernard J. Ortcutt is a Reddit moderation bot. Moderators send it commands by
reporting posts or comments. The bot reads these commands and automates
moderation, based on a customizable configuration.

## Setup ##

You can install the latest development version with:

    pip install https://github.com/leviroth/bernard/archive/master.zip

Your subreddit must be configured
for [toolbox's](https://github.com/creesch/reddit-moderator-toolbox/) usernotes
module, or else the built-in commands will fail.

The database should be set up by reading `create_tables.sql` with SQLite3, as
in:

    sqlite3 bernard-database.sq3 ".read create_tables.sql"

The bot requires `access`, `config`, `posts,` and `wiki` permissions. While not
strictly necessary, `mail` permissions keep replies to ban messages from going
to your bot's inbox. That makes it easier to isolate the messages sent to your
bot, which would be missed otherwise and which are very occasionally useful.

Login information should be configured with
a
[praw.ini file](http://praw.readthedocs.io/en/latest/getting_started/configuration/prawini.html).

## Usage ##

    python -m bernard [config_directory] [database]

## Configuration ##

The bot is configured via YAML files, one per subreddit. You can find an example
file in the `examples/` directory; given a directory containing the file
`thirdrealm.yaml`, the bot loads a configuration for the subreddit
`/r/ThirdRealm`.

A configuration file consists of a series of YAML documents, each one generating
a rule.

A rule configuration is a dictionary with three keys: `info`, `trigger`, and
`actions`.

### `info` configuration ###

Sample:

```yaml
info:
  name: Removed
  details: Question
```

The `info` block accepts `name` and `details` strings that summarize the rule.

### `trigger` configuration ###

Sample:

```yaml
trigger:
  commands:
  - question
  - q
  types:
  - post
```

The `trigger` block accepts a list of `commands`, which are strings that match
reports, and `types`, a list that can contain `post` and/or `comment`. In this
example, any post (but not comment) that is reported with the strings `question`
or `q` will be targeted for the action.

## `actions` configuration ##

Sample:

```yaml
actions:
- remove
- notify:
    text: 'Questions are best directed to /r/askphilosophy,  which specializes in
      answers to philosophical questions!'
- usernote:
    level: abusewarn
    text: Removed (question)
```

The `actions` block contains a list of action configurations. An action
configuration is either the name of an action, or else a dictionary wherein the
key is the name of the action and the value is a dictionary of parameters. The
parameters vary according to action, as described in the following section. If
the action is given as a string, then the parameters default to empty.

In this example, our rule performs three actions. The post is removed, a
notification is added explaining the removal, and a Reddit Moderator Toolbox
usernote is added to the submitter.

## Actions ##

Bernard understands the following basic actions, which can be composed into more
complex actions via a configuration file. A *target* can be a comment or a
submission.

### Removing targets ###

Set via the `remove` configuration key. Please note that the target is approved
otherwise; this is necessary to prevent repeat actions.

A submission that is removed is locked.

### Notifying authors ###

Via a comment, distinguished as a moderator. This comment is stickied if the
target is a submission.

### Automod update ###

Adds the author's username and/or post's domain to a list in the AutoModerator
configuration. This requires that the list include a placeholder name. I put
exclamation marks in my placeholders to ensure that they can't match a valid
username.

*Example uses*: Automatically report a problem user's comments for review;
automatically flair posts by bots or other specific-purpose accounts;
automatically remove spam domains.

### Ban authors ###

Bans the author from the subreddit. Can set a duration, but only on a fixed
per-command basis. That is, it isn't currently possible to make a report-command
take duration as a parameter. If no duration is set, the ban is permanent.

### Nuke replies ###

Removes all descendants from the comment tree. Does not affect the target; use
the `remove` key if it should be removed. Does not affect distinguished comments.

Currently only works for comment targets.

### Add toolbox usernote ###

Adds a usernote for the author.

## Logging ##

Bernard logs its actions to a
database. [bernard-logs](https://github.com/leviroth/bernard-logs) is a simple
Flask app providing a web-based view for these logs. reddit's OAuth is used for
login: a user can view the logs of a specific subreddit if and only if she is a
moderator of that subreddit.

## Namesake ##

Bernard J. Ortcutt is a character who appears in W. V. Quine's classic paper
"Quantifiers and Propositional Attitudes." This doesn't have anything to do with
what the bot does; I was just reading the paper back when I began this project,
and I needed a name.

## License ##

MIT
