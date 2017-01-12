class Browser:
    def __init__(self, actors, subreddit, db, cursor):
        self.actors = actors
        self.subreddit = subreddit
        self.db = db
        self.cursor = cursor

    def check_command(self, command, mod, post):
        for actor in self.rules:
            actor.parse(command, mod, post)

    def scan_reports(self):
        try:
            for post in self.subreddit.mod.reports(limit=None):
                for mod_report in post.mod_reports:
                    yield (mod_report[0], mod_report[1], post)
        except Exception as e:
            logging.error("Error fetching reports: {err}".format(err=e))

    def run(self):
        for command, mod, post in self.scan_reports():
            self.check_command(command, mod, post)
        for actor in self.rules:
            actor.after()
