import unittest
import json
import praw
import sqlite3
import betamax
import time
from base64 import b64encode
from betamax_serializers import pretty_json

import sys
sys.path.append('bernard/')


def _sleep(*args):
    raise Exception('Call to sleep')


time.sleep = _sleep


def b64_string(input_string):
    """Return a base64 encoded string (not bytes) from input_string."""
    return b64encode(input_string.encode('utf-8')).decode('utf-8')


def filter_access_token(interaction, current_cassette):
    """Add Betamax placeholder to filter access token."""
    request_uri = interaction.data['request']['uri']
    response = interaction.data['response']
    if ('api/v1/access_token' not in request_uri or
            response['status']['code'] != 200):
        return
    body = response['body']['string']
    try:
        token = json.loads(body)['access_token']
    except (KeyError, TypeError, ValueError):
        return
    current_cassette.placeholders.append(
            betamax.cassette.cassette.Placeholder(
                placeholder='<ACCESS_TOKEN>', replace=token))


class BJOTest(unittest.TestCase):
    def configure(self):
        self.r = praw.Reddit(
            user_agent="Tests for BernardJOrtcutt - levimroth@gmail.com")
        placeholders = {
            x: getattr(self.r.config, x)
            for x in "client_id client_secret username password".split()}
        placeholders['basic_auth'] = b64_string(
            '{}:{}'.format(placeholders['client_id'],
                           placeholders['client_secret']))
        betamax.Betamax.register_serializer(pretty_json.PrettyJSONSerializer)
        with betamax.Betamax.configure() as config:
            config.cassette_library_dir = 'tests/integration/cassettes'
            config.default_cassette_options['serialize_with'] = 'prettyjson'
            config.before_record(callback=filter_access_token)
            for key, value in placeholders.items():
                config.define_cassette_placeholder('<{}>'.format(key.upper()),
                                                   value)

        self.subreddit = self.r.subreddit('thirdrealm')
        self.db = sqlite3.connect(':memory:')
        self.cur = self.db.cursor()
        with open('create_tables.sql') as f:
            commands = f.read().split(';')
            for command in commands:
                self.cur.execute(command)

    def betamax_configure(self):
        http = self.r._core._requestor._http
        self.recorder = betamax.Betamax(http,
                                        cassette_library_dir='test/cassettes')

        http.headers['Accept-Encoding'] = 'identity'

    def setUp(self):
        self.configure()
        self.betamax_configure()
