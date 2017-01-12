class Browser:
    def __init__(self, rules, subreddit, db, cursor):
        self.rules = rules
        self.subreddit = subreddit
        self.db = db
        self.cursor = cursor

    def check_command(self, command, mod, post):
        for rule in self.rules:
            rule.parse(command, mod, post)

    def scan_reports(self):
        try:
            for post in self.subreddit.mod.reports(limit=None):
                for mod_report in post.mod_reports:
                    yield (mod_report[0], mod_report[1], post)
        except Exception as e:
            logging.error("Error fetching reports: {err}".format(err=e))

    def run(self):
        while True:
            try:
                for command, mod, post in self.scan_reports():
                    self.check_command(command, mod, post)
                for rule in self.rules:
                    rule.after()
                time.sleep(30)
            except KeyboardInterrupt:
                print("Stopped by keyboard")
                break
