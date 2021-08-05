from flask_restful import Api
from flask import Flask
from flask_cors import CORS
from flask_mail import Mail
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from flask_jwt_extended import JWTManager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from pymongo import MongoClient
import os

load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = os.environ.get('MAIL_PORT')
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['JWT_SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False
app.config['APCA_API_KEY_ID'] = os.environ.get('APCA_API_KEY_ID')
app.config['APCA_API_SECRET_KEY'] = os.environ.get('APCA_API_SECRET_KEY')
app.config['APCA_API_BASE_URL'] = os.environ.get('APCA_API_BASE_URL')

jobstores = {
    'default': MongoDBJobStore(database='buckets', collection='scheduled_jobs', client=MongoClient(os.environ.get("DATABASE_URL")))
}
job_defaults = {
    'coalesce': False,
    'max_instances': 3
}
executors = {
    'default': ThreadPoolExecutor(20),
    'processpool': ProcessPoolExecutor(5)
}

fernet = Fernet(os.environ.get('FERNET_ENCRYPTION_KEY'))
CORS(app)
scheduler = BackgroundScheduler(jobstores=jobstores, job_defaults=job_defaults, executors=executors)
scheduler.start()
api = Api(app)
jwt = JWTManager(app)
mail = Mail(app)