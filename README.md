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

    python -m bernard [command_config_file] [database]

## Configuration ##

Configuration is not currently well-documented, but much can be gleaned from the
`examples/` directory. Separate files are used for the reddit API login
information (JSON) and the command configuration (YAML).

Please note that the bot performs no validation of these configuration files.
You should not try to load configurations from untrusted sources, and even with
trusted sources you'll want to monitor startup to make sure that nothing has
crashed. Some basic validation can be performed manually via `schema.yaml`
and [pyKwalify](https://github.com/Grokzen/pykwalify).

The per-subreddit `default_post_actions` and `default_comment_actions` keys
allow automatic loading of the following defaults:

  - For
    each
    [subreddit rule](https://www.reddit.com/r/modnews/comments/42o2i0/moderators_subreddit_rules_now_available_for_all/) affecting
    posts, moderator reports using that rule as the report reason will result in
    the post being removed, the rule being posted as a notification, and a
    usernote being added for the user. These actions are also triggered by the
    commands `[i]` and `rule [i]`, where `[i]` is the number of the rule as it
    appears on the rules page.
  
  - For the *i*th comment-specific rule, the command `n [i]` or `nuke [i]`
    removes the comment and all its replies, adds a warning to follow the rule
    in question, and adds a usernote.

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

Adds the author's username to a list the AutoModerator configuration. This
requires that the list include a placeholder name. I put exclamation marks in my
placeholders to ensure that they can't match a valid username.

*Example uses*: Automatically report a problem user's comments for review;
automatically flair posts by bots or other specific-purpose accounts.

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
