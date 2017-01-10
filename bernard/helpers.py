def deserialize_thing_id(thing_id):
    return tuple(int(x, base=36) for x in thing_id[1:].split('_'))


def get_user_id(username, cursor, reddit):
    cursor.execute('SELECT id FROM users WHERE username=?', (username,))
    try:
        user_id = cursor.fetchone()[0]
    except TypeError:
        user_id_str = reddit.redditor(username).fullname
        _, user_id = deserialize_thing_id(user_id_str)

    return user_id
