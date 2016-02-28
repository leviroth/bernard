import web
import sqlite3

urls = (
        '/', 'index'
       )

sql = sqlite3.connect('sql.db', check_same_thread=False)
cur = sql.cursor()

class index:
    def GET(self):
        cur.execute('SELECT time, mod, action, reason FROM actions ORDER BY ROWID DESC')
        #rows = [(1,2),(3,4)]
        rows = cur.fetchall()
        return tmpl.index(rows)

tmpl = web.template.render('templates')

if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()
