"""
Project and Message API Routes
Handles CRUD operations for projects and messages
"""
from flask import Blueprint, request, jsonify
import logging
import jwt
import os
from app.database.mongodb import (
    create_project, get_user_projects, update_project, delete_project,
    save_message, get_project_messages, get_database_stats,
    create_tasks, get_project_tasks, update_task, delete_task
)

logger = logging.getLogger(__name__)
JWT_SECRET = os.getenv('FLASK_SECRET', 'change_this_secret')

project_bp = Blueprint('project', __name__)


@project_bp.route("/projects", methods=["GET"])
def get_projects():
    """Get all projects for the authenticated user"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Get user_id from JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        logger.info(f"📂 Fetching projects for user: {user_id}")
        
        projects = get_user_projects(user_id)
        
        return jsonify({
            "ok": True,
            "projects": projects
        })
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error fetching projects: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/projects", methods=["POST"])
def create_new_project():
    """Create a new project"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Get user_id from JWT token
        token = auth_header.replace('Bearer ', '')
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = payload['user_id']
        
        data = request.get_json()
        name = data.get('name')
        repo_data = data.get('repo')
        
        if not name:
            return jsonify({"error": "name required"}), 400
        
        logger.info(f"📝 Creating project '{name}' for user {user_id}")
        
        project = create_project(user_id, name, repo_data)
        
        if project:
            return jsonify({
                "ok": True,
                "project": project
            })
        else:
            return jsonify({"error": "Failed to create project"}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error creating project: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/projects/<project_id>", methods=["PUT"])
def update_project_route(project_id):
    """Update a project"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        data = request.get_json()
        
        # Remove fields that shouldn't be updated directly
        updates = {k: v for k, v in data.items() if k not in ['_id', 'id', 'user_id', 'created_at']}
        
        logger.info(f"✏️ Updating project {project_id}")
        
        success = update_project(project_id, updates)
        
        if success:
            return jsonify({"ok": True})
        else:
            return jsonify({"error": "Failed to update project"}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error updating project: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/projects/<project_id>", methods=["DELETE"])
def delete_project_route(project_id):
    """Delete a project"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        logger.info(f"🗑️ Deleting project {project_id}")
        
        success = delete_project(project_id)
        
        if success:
            return jsonify({"ok": True})
        else:
            return jsonify({"error": "Failed to delete project"}), 404
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error deleting project: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/projects/<project_id>/messages", methods=["GET"])
def get_messages(project_id):
    """Get all messages for a project"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        logger.info(f"💬 Fetching messages for project {project_id}")
        
        messages = get_project_messages(project_id)
        
        return jsonify({
            "ok": True,
            "messages": messages
        })
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error fetching messages: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/projects/<project_id>/messages", methods=["POST"])
def add_message(project_id):
    """Add a message to a project"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        data = request.get_json()
        role = data.get('role')  # 'user' or 'assistant'
        content = data.get('content')
        message_data = data.get('data')  # questions, plans, etc.
        
        if not role or not content:
            return jsonify({"error": "role and content required"}), 400
        
        logger.info(f"💬 Saving {role} message to project {project_id}")
        
        message = save_message(project_id, role, content, message_data)
        
        if message:
            return jsonify({
                "ok": True,
                "message": message
            })
        else:
            return jsonify({"error": "Failed to save message"}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error saving message: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/api/database/stats", methods=["GET"])
def database_stats():
    """Get database statistics"""
    try:
        stats = get_database_stats()
        return jsonify({
            "ok": True,
            "stats": stats
        })
    except Exception as e:
        logger.error(f"❌ Error getting database stats: {str(e)}")
        return jsonify({"error": str(e)}), 500


# ============== TASK OPERATIONS ==============

@project_bp.route("/projects/<project_id>/tasks", methods=["GET"])
def get_tasks(project_id):
    """Get all tasks for a project"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        status_filter = request.args.get('status')  # Optional status filter
        
        logger.info(f"📋 Fetching tasks for project {project_id}")
        
        tasks = get_project_tasks(project_id, status_filter)
        
        return jsonify({
            "ok": True,
            "tasks": tasks
        })
        
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error fetching tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/projects/<project_id>/tasks", methods=["POST"])
def create_project_tasks(project_id):
    """Create tasks for a project from AI-generated subtasks"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        data = request.get_json()
        subtasks = data.get('subtasks', [])
        session_id = data.get('session_id')
        
        if not subtasks:
            return jsonify({"error": "subtasks required"}), 400
        
        logger.info(f"✅ Creating {len(subtasks)} tasks for project {project_id}")
        
        task_ids = create_tasks(project_id, subtasks, session_id)
        
        if task_ids:
            return jsonify({
                "ok": True,
                "task_ids": task_ids,
                "count": len(task_ids)
            })
        else:
            return jsonify({"error": "Failed to create tasks"}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error creating tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/tasks/<task_id>", methods=["PUT"])
def update_task_route(task_id):
    """Update a task (e.g., status, assignee, etc.)"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        data = request.get_json()
        
        # Remove fields that shouldn't be updated directly
        updates = {k: v for k, v in data.items() if k not in ['_id', 'id', 'project_id', 'created_at', 'created_from']}
        
        logger.info(f"✏️ Updating task {task_id}")
        
        success = update_task(task_id, updates)
        
        if success:
            return jsonify({"ok": True})
        else:
            return jsonify({"error": "Failed to update task"}), 500
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error updating task: {str(e)}")
        return jsonify({"error": str(e)}), 500


@project_bp.route("/tasks/<task_id>", methods=["DELETE"])
def delete_task_route(task_id):
    """Delete a task"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "No authorization provided"}), 401
    
    try:
        # Verify JWT token
        token = auth_header.replace('Bearer ', '')
        jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        logger.info(f"🗑️ Deleting task {task_id}")
        
        success = delete_task(task_id)
        
        if success:
            return jsonify({"ok": True})
        else:
            return jsonify({"error": "Failed to delete task"}), 404
            
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        logger.error(f"❌ Error deleting task: {str(e)}")
        return jsonify({"error": str(e)}), 500


logger.info("✅ Project routes registered")

