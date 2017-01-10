CREATE TABLE users(
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE
);

CREATE TABLE modmails(
  id INTEGER PRIMARY KEY,
  author INTEGER,
  time DATETIME,
  body TEXT,
  subreddit INTEGER,
  FOREIGN KEY(author) REFERENCES users(id),
  FOREIGN KEY(subreddit) REFERENCES subreddits(id)
);

CREATE TABLE actions(
  id INTEGER PRIMARY KEY,
  target_type INTEGER,
  target_id INTEGER,
  action_summary TEXT,
  action_details TEXT,
  author INTEGER,
  moderator INTEGER,
  time DATETIME DEFAULT CURRENT_TIMESTAMP,
  subreddit INTEGER,
  FOREIGN KEY(author) REFERENCES users(id),
  FOREIGN KEY(moderator) REFERENCES users(id),
  FOREIGN KEY(subreddit) REFERENCES subreddits(id)
);

CREATE TABLE subreddits(
  id INTEGER PRIMARY KEY,
  display_name TEXT UNIQUE
);

CREATE TABLE subreddit_moderator(
  subreddit_id INTEGER,
  moderator_id INTEGER,
  FOREIGN KEY(subreddit_id) REFERENCES subreddits(id),
  FOREIGN KEY(moderator_id) REFERENCES users(id)
);

CREATE TABLE removals(
  action_id INTEGER,
  reinstated INTEGER DEFAULT 0,
  FOREIGN KEY(action_id) REFERENCES actions(id)
);

CREATE TABLE notifications(
  comment_id INTEGER PRIMARY KEY,
  action_id INTEGER,
  FOREIGN KEY(action_id) REFERENCES actions(id)
);
