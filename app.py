#!/usr/bin/env python3
from config import app
import routes

if __name__ == '__main__':
    #app.run()
    app.run(host='127.0.0.1', port='7000', debug=True)
