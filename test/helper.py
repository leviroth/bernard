import unittest
import json
import praw
import sqlite3


with open('test_config.json') as f:
    config = json.load(f)


class BJOTest(unittest.TestCase):
    def configure(self):
        self.r = praw.Reddit(client_id=config['client_id'],
                             client_secret=config['client_secret'],
                             user_agent=config['user_agent'],
                             username=config['username'],
                             password=config['password']
                             )
        self.subreddit = self.r.subreddit('thirdrealm')
        self.username = 'BJO_test_user'
        self.mod_username = 'BJO_test_mod'
        self.db = sqlite3.connect(':memory:')
        self.cur = self.db.cursor()
        with open('create_tables.sql') as f:
            commands = f.read().split(';')
            for command in commands:
                self.cur.execute(command)

    def setUp(self):
        self.configure()
