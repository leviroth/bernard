import web
import sqlite3

urls = (
        '/', 'index'
       )

sql = sqlite3.connect('sql.db', check_same_thread=False)
cur = sql.cursor()

class index:
    def GET(self):
        cur.execute('SELECT * FROM actions ORDER BY ROWID DESC')
        return str(cur.fetchall())

if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()
