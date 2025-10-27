from flask import Blueprint, request, jsonify
import logging
import uuid
from app.services.ai_service import analyze_task_with_llm, generate_implementation_plan, get_conversation_history
from app.services.github_service import get_user_repos, analyze_repo_structure
import requests as req

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

task_bp = Blueprint('task', __name__)

@task_bp.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    """Analyze task with repository context"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    logger.info("\n" + "="*80)
    logger.info("📥 ENDPOINT: /api/analyze")
    logger.info("="*80)
    
    try:
        body = request.get_json()
        logger.info(f"📦 Request Body: {body}")
        
        task = body.get('task')
        session_id = body.get('session_id') or str(uuid.uuid4())
        owner = body.get('owner')
        repo = body.get('repo')
        github_token = body.get('github_token')
        
        logger.info(f"📝 Task: {task}")
        logger.info(f"🔑 Session ID: {session_id}")
        logger.info(f"📦 Repo: {owner}/{repo}")
        
        if not task or not task.strip():
            logger.error("❌ No task provided")
            return jsonify({"error": "task required"}), 400
        
        # Fetch repo context if provided
        repo_context = None
        if owner and repo and github_token:
            logger.info("🔍 Fetching repository context...")
            repo_context = analyze_repo_structure(owner, repo, github_token)
            logger.info(f"✅ Context fetched: {len(repo_context.get('folders', {}))} folders")
        
        logger.info("🤖 Starting AI analysis...")
        result = analyze_task_with_llm(task, session_id, repo_context, owner, repo, github_token)
        
        logger.info(f"✅ Analysis Complete: {result}")
        
        response = {
            "session_id": session_id,
            "status": result.get('status'),
            "analysis": result.get('analysis'),
            "questions": result.get('questions'),
            "search_queries": result.get('search_queries')
        }
        
        logger.info(f"📤 Response: {response}")
        logger.info("="*80 + "\n")
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"❌ Error in analyze endpoint: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/generate_plan", methods=["POST", "OPTIONS"])
def generate_plan():
    """Generate implementation plan with or without answers"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    logger.info("\n" + "="*80)
    logger.info("📥 ENDPOINT: /api/generate_plan")
    logger.info("="*80)
    
    try:
        body = request.get_json()
        logger.info(f"📦 Request Body: {body}")
        
        task = body.get('task')
        answers = body.get('answers', {})
        session_id = body.get('session_id')
        team_members = body.get('team_members', [])
        
        logger.info(f"📝 Task: {task}")
        logger.info(f"💬 Answers: {answers}")
        logger.info(f"🔑 Session ID: {session_id}")
        logger.info(f"👥 Team Members: {team_members}")
        
        if not task or not task.strip():
            logger.error("❌ No task provided")
            return jsonify({"error": "task required"}), 400
        
        logger.info("🤖 Starting plan generation...")
        result = generate_implementation_plan(task, answers, session_id, team_members)
        
        logger.info(f"✅ Plan Generated: {result}")
        logger.info("="*80 + "\n")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error in generate_plan endpoint: {str(e)}")
        logger.exception("Full traceback:")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/github/repos", methods=["POST", "OPTIONS"])
def get_repos():
    """Get user's GitHub repositories"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        body = request.get_json()
        github_token = body.get('github_token')
        
        if not github_token:
            return jsonify({"error": "github_token required"}), 400
        
        repos = get_user_repos(github_token)
        return jsonify({"repos": repos})
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@task_bp.route("/conversation_history/<session_id>", methods=["GET", "OPTIONS"])
def get_history(session_id):
    """Get conversation history for a session"""
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200
    
    try:
        logger.info(f"📜 Fetching conversation history for session: {session_id}")
        history = get_conversation_history(session_id)
        logger.info(f"✅ Found {len(history.get('conversations', []))} conversations")
        return jsonify(history)
        
    except Exception as e:
        logger.error(f"❌ Error fetching history: {str(e)}")
        return jsonify({"error": str(e)}), 500


