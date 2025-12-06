from flask import Flask
from Admin.adminpanel_routes import register_admin_routes

def create_admin_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = "changeme-admin-secret"
    register_admin_routes(app)
    print(app.url_map)
    return app


