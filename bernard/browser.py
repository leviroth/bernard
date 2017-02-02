import logging


class Browser:
    "A class to fetch reports and dispatch to actors."
    def __init__(self, actors, subreddit, db, cursor):
        self.actors = actors
        self.subreddit = subreddit
        self.db = db
        self.cursor = cursor

    def check_command(self, command, mod, post):
        "Check if any actor matches this report."
        for actor in self.actors:
            actor.parse(command, mod, post)

    def reports(self):
        """Generator for mod reports in a subreddit.

        Yields tuple of report, mod name, and target.

        """
        try:
            for post in self.subreddit.mod.reports(limit=None):
                for mod_report in post.mod_reports:
                    yield (str(mod_report[0]), mod_report[1], post)
        except Exception as e:
            logging.error("Error fetching reports: {err}".format(err=e))

    def run(self):
        "Fetch reports and dispatch to actors."
        for command, mod, post in self.reports():
            self.check_command(command, mod, post)
        for actor in self.actors:
            actor.after()
