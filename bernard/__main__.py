"""Entry point for the bot."""
import logging
import sqlite3
import sys
import time

import praw
import prawcore

from . import helpers
from .loader import YAMLLoader

USER_AGENT = "python:/r/Philosophy reporter:v0.4.0 (by levimroth@gmail.com)"


def main():
    """Entry point for the bot."""
    if len(sys.argv) != 3:
        print("Usage: python -m bernard [configuration file] [database]")
        exit(1)
    # pylint: disable=unbalanced-tuple-unpacking
    _, subs_conf, db_file = sys.argv

    reddit = praw.Reddit(user_agent=USER_AGENT)
    database = sqlite3.connect(db_file)
    cursor = database.cursor()

    loader = YAMLLoader(database, reddit)
    browsers = loader.load(subs_conf)
    database.commit()

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
                    except prawcore.exceptions.RequestException as exception:
                        logging.error(exception)
                        database.rollback()
                    else:
                        database.commit()
                counter = 0
            else:
                counter += 1
            time.sleep(30)
        except KeyboardInterrupt:
            print("Keyboard interrupt; shutting down...")
            break


main()
