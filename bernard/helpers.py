def deserialize_thing_id(thing_id):
    "Convert base36 str representation of reddit 'thing id' into int tuple."
    return tuple(int(x, base=36) for x in thing_id[1:].split('_'))


def update_sr_tables(cursor, subreddit):
    "Update tables of subreddits and subreddit-moderator relationships."
    _, subreddit_id = deserialize_thing_id(subreddit.fullname)

    # Add subreddits and update subscriber counts
    cursor.execute(
        'INSERT OR IGNORE INTO subreddits (id, display_name) VALUES(?,?)',
        (subreddit_id, str(subreddit)))
    cursor.execute('UPDATE subreddits SET subscribers = ? '
                   'WHERE id = ?',
                   (subreddit.subscribers, subreddit_id))

    # Refresh listing of subreddits' moderators
    cursor.execute('DELETE FROM subreddit_moderator '
                   'WHERE subreddit_id = ?', (subreddit_id,))

    for moderator in subreddit.moderator:
        cursor.execute('INSERT OR IGNORE INTO users (username) '
                       'VALUES(?)', (str(moderator),))
        cursor.execute('SELECT id FROM users WHERE username = ?',
                       (str(moderator),))
        moderator_id = cursor.fetchone()[0]
        cursor.execute('INSERT OR IGNORE INTO subreddit_moderator '
                       '(subreddit_id, moderator_id) VALUES(?,?)',
                       (subreddit_id, moderator_id))
