import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import init_db, SessionLocal, Admin
from passlib.hash import argon2

def create_admin(username, password):
    db = SessionLocal()
    hashed_pw = argon2.hash(password)

    admin = Admin(username=username, password_hash=hashed_pw)  # fixed fields
    db.add(admin)
    db.commit()
    db.close()
    print("Admin created successfully!")

if __name__ == "__main__":
    init_db()
    username = input("Enter admin username: ")   # changed from email
    password = input("Enter password: ")
    create_admin(username, password)
