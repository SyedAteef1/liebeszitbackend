import requests
from flask import Blueprint, request, jsonify, redirect, session
from datetime import datetime
from app.config import Config
from bson.objectid import ObjectId
import logging
import jwt
import os

logger = logging.getLogger(__name__)
github_bp = Blueprint('github', __name__)
users_collection = None
JWT_SECRET = os.getenv('FLASK_SECRET', 'change_this_secret')

def get_users_collection():
    global users_collection
    if users_collection is None:
        from app.database.mongodb import db
        users_collection = db['users']
        users_collection.create_index([("email", 1)], unique=True)
    return users_collection

def save_github_token(user_id, access_token, username, github_user_id):
    try:
        collection = get_users_collection()
        collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                "github_token": access_token,
                "github_username": username,
                "github_id": github_user_id,
                "github_connected": True,
                "updated_at": datetime.utcnow()
            }}
        )
        logger.info(f"GitHub token saved for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving GitHub token: {str(e)}")
        return False

@github_bp.route("/install", methods=["GET"])
def github_install():
    logger.info("=== GITHUB INSTALL INITIATED ===")
    
    # Get JWT token from query parameter
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "No authentication token provided"}), 401
    
    try:
        # Verify JWT and extract user_id
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        # Store user_id in session for callback
        session['pending_github_user_id'] = user_id
        session['auth_token'] = token
        
        logger.info(f"GitHub OAuth initiated for user: {user_id}")
        
        import secrets
        state = secrets.token_hex(8)
        session['github_state'] = state
        
        auth_url = (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={Config.GITHUB_CLIENT_ID}&"
            f"scope=repo&"
            f"state={state}&"
            f"redirect_uri={Config.BACKEND_URL}/github/callback"
        )
        
        logger.info(f"Redirect to: {auth_url}")
        return redirect(auth_url)
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

@github_bp.route("/callback", methods=["GET"])
def github_callback():
    logger.info("=== GITHUB CALLBACK RECEIVED ===")
    
    code = request.args.get("code")
    error = request.args.get("error")
    state = request.args.get("state")
    
    if error:
        logger.error(f"OAuth error: {error}")
        return redirect(f"{Config.FRONTEND_URL}/github?error={error}")
    
    if not code:
        logger.error("No authorization code received")
        return redirect(f"{Config.FRONTEND_URL}/github?error=no_code")
    
    # Verify state to prevent CSRF
    if state != session.get('github_state'):
        logger.error("State mismatch - possible CSRF attack")
        return redirect(f"{Config.FRONTEND_URL}/github?error=invalid_state")
    
    # Get the authenticated user_id from session
    user_id = session.get('pending_github_user_id')
    if not user_id:
        logger.error("No user_id in session")
        return redirect(f"{Config.FRONTEND_URL}/github?error=session_expired")
    
    logger.info(f"Authorization code received for user: {user_id}")
    
    try:
        token_url = "https://github.com/login/oauth/access_token"
        data = {
            'client_id': Config.GITHUB_CLIENT_ID,
            'client_secret': Config.GITHUB_CLIENT_SECRET,
            'code': code
        }
        headers = {'Accept': 'application/json'}
        
        logger.info("Exchanging code for token...")
        response = requests.post(token_url, json=data, headers=headers)
        result = response.json()
        
        if 'access_token' not in result:
            error_msg = result.get('error', 'unknown_error')
            logger.error(f"Token exchange failed: {error_msg}")
            return redirect(f"{Config.FRONTEND_URL}/github?error={error_msg}")
        
        access_token = result['access_token']
        
        # Get GitHub user info
        user_url = "https://api.github.com/user"
        user_headers = {'Authorization': f'token {access_token}'}
        user_response = requests.get(user_url, headers=user_headers)
        user_data = user_response.json()
        
        username = user_data.get('login')
        github_user_id = user_data.get('id')
        
        # Save token to the AUTHENTICATED user (not GitHub user_id)
        save_github_token(user_id, access_token, username, github_user_id)
        
        # Clear session
        session.pop('pending_github_user_id', None)
        session.pop('github_state', None)
        
        logger.info("GitHub token exchange successful!")
        logger.info(f"Username: {username}")
        logger.info(f"Saved to user: {user_id}")
        
        # Redirect back to demodash page with success message
        return redirect(f"{Config.FRONTEND_URL}/demodash?github_connected=true")
        
    except Exception as e:
        logger.error(f"Exception during token exchange: {str(e)}")
        return redirect(f"{Config.FRONTEND_URL}/github?error=exchange_failed")

@github_bp.route("/api/repos", methods=["GET"])
def get_repos():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Get user's JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        # Get user's GitHub token from database
        collection = get_users_collection()
        user = collection.find_one({"_id": ObjectId(user_id)})
        
        if not user or not user.get('github_token'):
            return jsonify({"error": "GitHub not connected"}), 401
        
        github_token = user['github_token']
        headers = {'Authorization': f'token {github_token}'}
        url = "https://api.github.com/user/repos?per_page=100&sort=updated"
        
        response = requests.get(url, headers=headers)
        repos = response.json()
        
        formatted_repos = [{
            'id': repo['id'],
            'name': repo['name'],
            'full_name': repo['full_name'],
            'description': repo.get('description'),
            'language': repo.get('language'),
            'private': repo['private'],
            'updated_at': repo['updated_at']
        } for repo in repos if isinstance(repo, dict)]
        
        return jsonify(formatted_repos)
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"Error fetching repos: {str(e)}")
        return jsonify({"error": str(e)}), 500

@github_bp.route("/api/check_connection", methods=["GET"])
def check_connection():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"connected": False})
    
    try:
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        collection = get_users_collection()
        user = collection.find_one({"_id": ObjectId(user_id)})
        
        if user and user.get('github_token'):
            # Verify token is still valid
            github_token = user['github_token']
            headers = {'Authorization': f'token {github_token}'}
            response = requests.get("https://api.github.com/user", headers=headers)
            
            if response.status_code == 200:
                return jsonify({"connected": True})
        
        return jsonify({"connected": False})
        
    except Exception as e:
        logger.error(f"Error checking connection: {str(e)}")
        return jsonify({"connected": False})
