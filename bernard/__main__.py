"""Entry point for the bot."""
import logging
import sqlite3
import sys
import time
from pathlib import Path

import praw
import prawcore

from . import helpers
from .loader import load_yaml_config

USER_AGENT = "python:/r/Philosophy reporter:v0.4.0 (by levimroth@gmail.com)"


def main():
    """Entry point for the bot."""
    if len(sys.argv) != 3:
        print("Usage: python -m bernard [configuration file] [database]")
        exit(1)
    # pylint: disable=unbalanced-tuple-unpacking
    _, conf_dir, db_file = sys.argv

    reddit = praw.Reddit(user_agent=USER_AGENT)
    database = sqlite3.connect(db_file)
    cursor = database.cursor()

    browsers = []
    for config_file in Path(conf_dir).glob('*.yaml'):
        sub_name, _ = config_file.name.rsplit('.', 1)
        subreddit = reddit.subreddit(sub_name)
        browsers.append(load_yaml_config(database, subreddit, config_file))
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
                    except prawcore.PrawcoreException as exception:
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
