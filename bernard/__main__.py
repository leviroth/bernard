import json
import logging
import praw
import sqlite3
import sys
import time

from . import helpers, loader

_, subs_conf, db_file = sys.argv

USER_AGENT = "python:/r/Philosophy reporter:v0.4.0 (by levimroth@gmail.com)"
r = praw.Reddit(user_agent=USER_AGENT)
db = sqlite3.connect(db_file)
cursor = db.cursor()

loader = loader.YAMLLoader(db, cursor, r)
browsers = loader.load(subs_conf)
db.commit()

print("Loaded")

counter = 0
while True:
    try:
        for browser in browsers:
            browser.run()
        if counter == 20:
            for browser in browsers:
                try:
                    helpers.update_sr_tables(cursor, browser.subreddit)
                except Exception as e:
                    logging.error(e)
                    db.rollback()
                else:
                    db.commit()
            counter = 0
        else:
            counter += 1
        time.sleep(30)
    except KeyboardInterrupt:
        print("Keyboard interrupt; shutting down...")
        break
