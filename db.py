from pymongo import MongoClient
import os

connection = MongoClient(os.environ.get("DATABASE_URL"))
db = connection[os.environ.get("DATABASE_NAME")]