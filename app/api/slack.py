"""
Slack API Routes
Handles Slack OAuth and messaging
"""
from flask import Blueprint, request, redirect, jsonify, session
import logging
import requests
import json
from urllib.parse import urlencode
from datetime import datetime
from app.config import Config
import jwt
import os

logger = logging.getLogger(__name__)
slack_bp = Blueprint('slack', __name__)
JWT_SECRET = os.getenv('FLASK_SECRET', 'change_this_secret')

tokens_collection = None

def get_tokens_collection():
    """Get tokens collection (lazy initialization)"""
    global tokens_collection
    if tokens_collection is None:
        from app.database.mongodb import db
        tokens_collection = db['slack_tokens']
        tokens_collection.create_index([("user_id", 1)], unique=True)
    return tokens_collection

def save_token(user_id, team_id, access_token, scope, bot_token=None):
    """Save Slack token to database linked to authenticated user"""
    try:
        collection = get_tokens_collection()
        collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "team_id": team_id,
                    "access_token": access_token,
                    "scope": scope,
                    "bot_token": bot_token,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        logger.info(f"✅ Slack token saved for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving token: {str(e)}")
        return False

def get_token_for_user(user_id):
    """Get Slack token for user"""
    try:
        collection = get_tokens_collection()
        token_doc = collection.find_one({"user_id": user_id})
        return token_doc
    except Exception as e:
        logger.error(f"❌ Error getting token: {str(e)}")
        return None

@slack_bp.route("/install", methods=["GET"])
def slack_install():
    """Initiate Slack OAuth flow"""
    logger.info("="*60)
    logger.info("=== SLACK INSTALL INITIATED ===")
    
    # Get JWT token from query parameter
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "No authentication token provided"}), 401
    
    try:
        # Verify JWT and extract user_id
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        # Store user_id in session for callback
        session['pending_slack_user_id'] = user_id
        session['auth_token'] = token
        
        logger.info(f"Slack OAuth initiated for user: {user_id}")
        
        # Generate state for CSRF protection
        import secrets
        state = secrets.token_hex(8)
        session['slack_state'] = state
        
        params = {
            "client_id": Config.SLACK_CLIENT_ID,
            "scope": (
                "app_mentions:read,bookmarks:read,assistant:write,canvases:read,"
                "canvases:write,channels:read,channels:join,groups:read,"
                "channels:history,groups:history,im:history,im:read,mpim:history,"
                "chat:write,users:read,team:read"
            ),
            "redirect_uri": f"{Config.BACKEND_URL}/slack/oauth_redirect",
            "state": state
        }
        
        auth_url = f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"
        logger.info(f"🔗 Redirect to: {auth_url}")
        logger.info("="*60)
        
        return redirect(auth_url)
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

@slack_bp.route("/oauth_redirect", methods=["GET"])
def slack_oauth_redirect():
    """Handle Slack OAuth callback"""
    logger.info("="*60)
    logger.info("=== OAUTH REDIRECT RECEIVED ===")
    
    code = request.args.get("code")
    error = request.args.get("error")
    state = request.args.get("state")
    
    if error:
        logger.error(f"❌ OAuth error: {error}")
        return redirect(f"{Config.FRONTEND_URL}/slack?error={error}")
    
    if not code:
        logger.error("❌ No authorization code received")
        return redirect(f"{Config.FRONTEND_URL}/slack?error=no_code")
    
    # Verify state to prevent CSRF
    if state != session.get('slack_state'):
        logger.error("State mismatch - possible CSRF attack")
        return redirect(f"{Config.FRONTEND_URL}/slack?error=invalid_state")
    
    # Get the authenticated user_id from session
    user_id = session.get('pending_slack_user_id')
    if not user_id:
        logger.error("No user_id in session")
        return redirect(f"{Config.FRONTEND_URL}/slack?error=session_expired")
    
    logger.info(f"✅ Authorization code received for user: {user_id}")
    
    # Exchange code for token
    try:
        token_url = "https://slack.com/api/oauth.v2.access"
        data = {
            "client_id": Config.SLACK_CLIENT_ID,
            "client_secret": Config.SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": f"{Config.BACKEND_URL}/slack/oauth_redirect"
        }
        
        logger.info("📡 Exchanging code for token...")
        response = requests.post(token_url, data=data)
        result = response.json()
        
        logger.info(f"📦 Token exchange response: {json.dumps(result, indent=2)}")
        
        if not result.get("ok"):
            error_msg = result.get("error", "unknown_error")
            logger.error(f"❌ Token exchange failed: {error_msg}")
            return redirect(f"{Config.FRONTEND_URL}/slack?error={error_msg}")
        
        # Save token to the AUTHENTICATED user
        team_id = result["team"]["id"]
        access_token = result.get("access_token")
        bot_token = result.get("access_token")
        scope = result.get("scope", "")
        
        from datetime import datetime
        save_token(user_id, team_id, access_token, scope, bot_token)
        
        # Clear session
        session.pop('pending_slack_user_id', None)
        session.pop('slack_state', None)
        
        logger.info("✅ Token exchange successful!")
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"🏢 Team ID: {team_id}")
        logger.info("="*60)
        
        # Redirect back to test page with success message
        return redirect(f"{Config.FRONTEND_URL}/test?slack_connected=true")
        
    except Exception as e:
        logger.error(f"❌ Exception during token exchange: {str(e)}")
        return redirect(f"{Config.FRONTEND_URL}/slack?error=exchange_failed")

@slack_bp.route("/api/list_conversations", methods=["GET"])
def list_conversations():
    """List Slack conversations for authenticated user"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Get user's JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        token_info = get_token_for_user(user_id)
        if not token_info:
            return jsonify({"error": "Slack not connected"}), 404
        
        slack_token = token_info.get("bot_token") or token_info.get("access_token")
        
        url = "https://slack.com/api/conversations.list"
        headers = {"Authorization": f"Bearer {slack_token}"}
        params = {"types": "public_channel,private_channel"}
        
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if not data.get("ok"):
            return jsonify({"error": data.get("error", "unknown")}), 400
        
        channels = data.get("channels", [])
        return jsonify({"channels": channels})
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error listing conversations: {str(e)}")
        return jsonify({"error": str(e)}), 500

@slack_bp.route("/api/status", methods=["GET"])
def slack_status():
    """Check if user has Slack connected"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"connected": False}), 200
    
    try:
        # Get user's JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        # Check if user has Slack token
        token_info = get_token_for_user(user_id)
        
        if token_info and token_info.get('access_token'):
            logger.info(f"✅ Slack connected for user: {user_id}")
            return jsonify({
                "connected": True,
                "slack_user_id": user_id,
                "team_id": token_info.get('team_id')
            })
        else:
            logger.info(f"❌ Slack not connected for user: {user_id}")
            return jsonify({"connected": False})
            
    except jwt.ExpiredSignatureError:
        return jsonify({"connected": False, "error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"connected": False, "error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error checking Slack status: {str(e)}")
        return jsonify({"connected": False, "error": str(e)}), 500

@slack_bp.route("/api/channel_history", methods=["GET"])
def get_channel_history():
    """Get message history from a Slack channel"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401

    try:
        # Get user's JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']

        slack_token_doc = get_token_for_user(user_id)
        if not slack_token_doc or not slack_token_doc.get('access_token'):
            return jsonify({"error": "Slack not connected for this user"}), 400
        
        slack_access_token = slack_token_doc['access_token']
        
        channel_id = request.args.get("channel")
        limit = request.args.get("limit", "50")  # Default last 50 messages
        
        if not channel_id:
            return jsonify({"error": "Channel ID required"}), 400

        # Get messages from Slack API
        url = "https://slack.com/api/conversations.history"
        headers = {"Authorization": f"Bearer {slack_access_token}"}
        params = {"channel": channel_id, "limit": limit}
        
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if data.get("ok"):
            messages = data.get("messages", [])
            
            # Get user info for each message
            user_cache = {}
            enriched_messages = []
            
            for msg in messages:
                user_id_msg = msg.get("user")
                if user_id_msg and user_id_msg not in user_cache:
                    # Fetch user info
                    user_url = "https://slack.com/api/users.info"
                    user_response = requests.get(user_url, headers=headers, params={"user": user_id_msg})
                    user_data = user_response.json()
                    if user_data.get("ok"):
                        user_cache[user_id_msg] = user_data.get("user", {}).get("real_name", "Unknown")
                    else:
                        user_cache[user_id_msg] = "Unknown"
                
                enriched_messages.append({
                    "text": msg.get("text", ""),
                    "user": user_cache.get(msg.get("user"), "Bot"),
                    "timestamp": msg.get("ts", ""),
                    "type": msg.get("type", "message")
                })
            
            return jsonify({"ok": True, "messages": enriched_messages})
        else:
            logger.error(f"❌ Slack API error: {data.get('error')}")
            return jsonify({"error": data.get("error", "Unknown Slack API error")}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error fetching channel history: {str(e)}")
        return jsonify({"error": str(e)}), 500

@slack_bp.route("/api/summarize_channel", methods=["POST"])
def summarize_channel():
    """Generate AI summary of Slack channel messages"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401

    try:
        # Get user's JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        body = request.get_json()
        messages = body.get("messages", [])
        
        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        # Call AI service to generate summary
        from app.services.ai_service import summarize_slack_messages
        
        summary = summarize_slack_messages(messages)
        
        return jsonify({"ok": True, "summary": summary})
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error generating summary: {str(e)}")
        return jsonify({"error": str(e)}), 500

@slack_bp.route("/api/send_message", methods=["POST"])
def send_message():
    """Send a message to Slack"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    body = request.get_json()
    channel = body.get("channel")
    text = body.get("text")
    mention_user_id = body.get("mention_user_id")
    
    logger.info("=== SEND MESSAGE REQUEST ===")
    logger.info(f"Channel: {channel}")
    logger.info(f"Message: {text}")
    
    if not channel or not text:
        return jsonify({"error": "channel and text required"}), 400
    
    try:
        # Get user's JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        token_info = get_token_for_user(user_id)
        if not token_info:
            return jsonify({"error": "Slack not connected"}), 404
        
        slack_token = token_info.get("bot_token") or token_info.get("access_token")
        
        # Join channel first
        try:
            join_url = "https://slack.com/api/conversations.join"
            join_headers = {"Authorization": f"Bearer {slack_token}", "Content-Type": "application/json"}
            join_payload = {"channel": channel}
            requests.post(join_url, headers=join_headers, json=join_payload)
        except Exception as e:
            logger.warning(f"⚠️ Could not join channel: {str(e)}")
        
        # Send message
        final_text = text
        if mention_user_id:
            final_text = f"<@{mention_user_id}> {text}"
        
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {slack_token}", "Content-Type": "application/json"}
        payload = {"channel": channel, "text": final_text}
        
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        
        logger.info(f"Slack response: {json.dumps(data, indent=2)}")
        
        return jsonify(data)
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error sending message: {str(e)}")
        return jsonify({"error": str(e)}), 500
