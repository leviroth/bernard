"""Provide the Browser class."""
import logging

import prawcore


class Browser:
    """A class to fetch reports and dispatch to rules."""

    def __init__(self, rules, buffers, subreddit, database):
        """Initialize the Browser class."""
        self.rules = rules
        self.buffers = buffers
        self.subreddit = subreddit
        self.database = database

    def check_command(self, command, mod, post):
        """Check if any rule matches this report."""
        for rule in self.rules:
            rule.parse(command, mod, post)

    def reports(self):
        """Generate mod reports for a subreddit.

        Yields tuple of report, mod name, and target.

        """
        try:
            for post in self.subreddit.mod.reports(limit=None):
                for mod_report in post.mod_reports:
                    yield (str(mod_report[0]), mod_report[1], post)
        except prawcore.PrawcoreException as exception:
            logging.error("Error fetching reports: %s", exception)

    def run(self):
        """Fetch reports and dispatch to actors."""
        for command, mod, post in self.reports():
            self.check_command(command, mod, post)
        for buffer in self.buffers:
            buffer.after()
