from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import jwt
import os

auth_bp = Blueprint('auth', __name__)
JWT_SECRET = os.getenv('FLASK_SECRET', 'change_this_secret')

users_collection = None


def get_users_collection():
    """Get users collection (lazy initialization)"""
    global users_collection
    if users_collection is None:
        from app.database.mongodb import db
        users_collection = db['users']
        users_collection.create_index([("email", 1)], unique=True)
    return users_collection

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    collection = get_users_collection()
    if collection.find_one({"email": email}):
        return jsonify({"error": "Email already exists"}), 400
    
    user = {
        "email": email,
        "password": generate_password_hash(password),
        "name": name or email.split("@")[0],
        "created_at": datetime.utcnow()
    }
    
    result = collection.insert_one(user)
    user_id = str(result.inserted_id)
    
    token = jwt.encode({
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=30)
    }, JWT_SECRET, algorithm="HS256")
    
    return jsonify({
        "ok": True,
        "token": token,
        "user": {"id": user_id, "email": email, "name": user["name"]}
    })

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    collection = get_users_collection()
    user = collection.find_one({"email": email})
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    user_id = str(user["_id"])
    
    token = jwt.encode({
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=30)
    }, JWT_SECRET, algorithm="HS256")
    
    return jsonify({
        "ok": True,
        "token": token,
        "user": {"id": user_id, "email": email, "name": user.get("name", email)}
    })

@auth_bp.route("/logout", methods=["POST"])
def logout():
    return jsonify({"ok": True})

@auth_bp.route("/me", methods=["GET"])
def get_current_user():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({"authenticated": False}), 401
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        collection = get_users_collection()
        user = collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"authenticated": False}), 401
        
        has_github = bool(user.get("github_token"))
        print(f"User {user['email']} - GitHub token exists: {has_github}")
        
        return jsonify({
            "authenticated": True,
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "name": user.get("name", user["email"]),
                "github_connected": has_github
            }
        })
    except jwt.ExpiredSignatureError:
        return jsonify({"authenticated": False, "error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"authenticated": False, "error": "Invalid token"}), 401
