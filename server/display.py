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
        body = "<html><head><title>foo</title></head><body><table>"
        for row in cur.fetchall():
            body += "<tr>"
            for col in row:
                body += "<td>" + str(col) + "</td>"
            body += "</tr>"
        body += "</table></body></html>"

        return body

if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()
