"""
MongoDB Database Layer for Feeta
Handles all database operations for projects, messages, and repo context
"""
import os
import logging
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

# MongoDB Client
client = None
db = None

# Collections
users_collection = None
projects_collection = None
messages_collection = None
repo_context_collection = None
conversation_history_collection = None
tasks_collection = None


def init_db():
    """Initialize MongoDB connection and create indexes"""
    global client, db, users_collection, projects_collection, messages_collection
    global repo_context_collection, conversation_history_collection, tasks_collection
    
    try:
        logger.info("🔌 Connecting to MongoDB...")
        # Add timeout and retry settings
        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,  # 5 second timeout
            connectTimeoutMS=10000,  # 10 second connection timeout
            socketTimeoutMS=10000,  # 10 second socket timeout
            maxPoolSize=10,
            retryWrites=True
        )
        
        # Test the connection
        client.admin.command('ping')
        logger.info("✅ MongoDB connection successful!")
        
        db = client['feeta']
        
        # Initialize collections
        users_collection = db['users']
        projects_collection = db['projects']
        messages_collection = db['messages']
        repo_context_collection = db['repo_contexts']
        conversation_history_collection = db['conversation_history']
        tasks_collection = db['tasks']
        
        # Create indexes for performance
        users_collection.create_index([("email", ASCENDING)], unique=True)
        projects_collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        messages_collection.create_index([("project_id", ASCENDING), ("created_at", ASCENDING)])
        repo_context_collection.create_index([("repo_full_name", ASCENDING)], unique=True)
        conversation_history_collection.create_index([("session_id", ASCENDING)], unique=True)
        tasks_collection.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])
        tasks_collection.create_index([("status", ASCENDING)])
        
        logger.info("✅ MongoDB collections initialized with indexes")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize MongoDB: {str(e)}")
        raise


# ============== USER OPERATIONS ==============

def create_or_update_user(user_id, email, name, github_data=None):
    """Create or update a user in the database"""
    try:
        user_data = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "updated_at": datetime.utcnow()
        }
        
        if github_data:
            user_data["github_connected"] = True
            user_data["github_username"] = github_data.get("login")
            user_data["github_token"] = github_data.get("token")
            user_data["github_id"] = github_data.get("id")
        
        result = users_collection.update_one(
            {"user_id": user_id},
            {"$set": user_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
        
        logger.info(f"✅ User {user_id} saved to database")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving user: {str(e)}")
        return False


def get_user(user_id):
    """Get user from database"""
    try:
        user = users_collection.find_one({"user_id": user_id})
        if user:
            user['_id'] = str(user['_id'])
        return user
    except Exception as e:
        logger.error(f"❌ Error getting user: {str(e)}")
        return None


# ============== PROJECT OPERATIONS ==============

def create_project(user_id, name, repo_data=None):
    """Create a new project"""
    try:
        project = {
            "user_id": user_id,
            "name": name,
            "repo": repo_data,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = projects_collection.insert_one(project)
        project['_id'] = str(result.inserted_id)
        project['id'] = str(result.inserted_id)
        
        logger.info(f"✅ Project '{name}' created for user {user_id}")
        return project
    except Exception as e:
        logger.error(f"❌ Error creating project: {str(e)}")
        return None


def get_user_projects(user_id):
    """Get all projects for a user"""
    try:
        projects = list(projects_collection.find(
            {"user_id": user_id}
        ).sort("created_at", DESCENDING))
        
        for project in projects:
            project['_id'] = str(project['_id'])
            project['id'] = str(project['_id'])
            
            # Get message count for each project
            msg_count = messages_collection.count_documents({"project_id": project['id']})
            project['message_count'] = msg_count
        
        logger.info(f"✅ Found {len(projects)} projects for user {user_id}")
        return projects
    except Exception as e:
        logger.error(f"❌ Error getting projects: {str(e)}")
        return []


def update_project(project_id, updates):
    """Update a project"""
    try:
        updates['updated_at'] = datetime.utcnow()
        
        result = projects_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": updates}
        )
        
        if result.modified_count > 0:
            logger.info(f"✅ Project {project_id} updated")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Error updating project: {str(e)}")
        return False


def delete_project(project_id):
    """Delete a project and its messages and tasks"""
    try:
        # Delete all messages for this project
        messages_collection.delete_many({"project_id": project_id})
        
        # Delete all tasks for this project
        tasks_collection.delete_many({"project_id": project_id})
        
        # Delete the project
        result = projects_collection.delete_one({"_id": ObjectId(project_id)})
        
        if result.deleted_count > 0:
            logger.info(f"✅ Project {project_id} deleted")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Error deleting project: {str(e)}")
        return False


# ============== MESSAGE OPERATIONS ==============

def save_message(project_id, role, content, data=None):
    """Save a message to the database"""
    try:
        message = {
            "project_id": project_id,
            "role": role,  # 'user' or 'assistant'
            "content": content,
            "data": data,  # Store questions, plans, etc.
            "created_at": datetime.utcnow()
        }
        
        result = messages_collection.insert_one(message)
        message['_id'] = str(result.inserted_id)
        message['id'] = str(result.inserted_id)
        
        # Update project's updated_at timestamp
        projects_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"✅ Message saved to project {project_id}")
        return message
    except Exception as e:
        logger.error(f"❌ Error saving message: {str(e)}")
        return None


def get_project_messages(project_id):
    """Get all messages for a project"""
    try:
        messages = list(messages_collection.find(
            {"project_id": project_id}
        ).sort("created_at", ASCENDING))
        
        for message in messages:
            message['_id'] = str(message['_id'])
            message['id'] = str(message['_id'])
        
        logger.info(f"✅ Found {len(messages)} messages for project {project_id}")
        return messages
    except Exception as e:
        logger.error(f"❌ Error getting messages: {str(e)}")
        return []


# ============== REPO CONTEXT OPERATIONS ==============

def save_repo_context(repo_full_name, context_text, language=None, metadata=None):
    """Save GitHub repo context for reuse"""
    try:
        repo_context = {
            "repo_full_name": repo_full_name,
            "context_text": context_text,
            "language": language,
            "metadata": metadata or {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "access_count": 0
        }
        
        result = repo_context_collection.update_one(
            {"repo_full_name": repo_full_name},
            {
                "$set": repo_context,
                "$inc": {"access_count": 1}
            },
            upsert=True
        )
        
        logger.info(f"✅ Repo context saved for {repo_full_name}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving repo context: {str(e)}")
        return False


def get_repo_context(repo_full_name):
    """Get cached repo context"""
    try:
        context = repo_context_collection.find_one({"repo_full_name": repo_full_name})
        
        if context:
            # Increment access count
            repo_context_collection.update_one(
                {"repo_full_name": repo_full_name},
                {"$inc": {"access_count": 1}}
            )
            
            context['_id'] = str(context['_id'])
            logger.info(f"✅ Repo context found for {repo_full_name} (cached)")
            return context
        
        logger.info(f"ℹ️ No cached context for {repo_full_name}")
        return None
    except Exception as e:
        logger.error(f"❌ Error getting repo context: {str(e)}")
        return None


def update_repo_context(repo_full_name, context_text):
    """Update existing repo context"""
    try:
        result = repo_context_collection.update_one(
            {"repo_full_name": repo_full_name},
            {
                "$set": {
                    "context_text": context_text,
                    "updated_at": datetime.utcnow()
                },
                "$inc": {"access_count": 1}
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"✅ Repo context updated for {repo_full_name}")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Error updating repo context: {str(e)}")
        return False


# ============== CONVERSATION HISTORY OPERATIONS ==============

def save_conversation_history(session_id, prompt, analysis=None, plan=None):
    """Save conversation history to database"""
    try:
        conversation_entry = {
            "timestamp": datetime.utcnow(),
            "prompt": prompt,
            "analysis": analysis,
            "plan": plan
        }
        
        result = conversation_history_collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"conversations": conversation_entry},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
        
        logger.info(f"✅ Conversation saved for session {session_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving conversation history: {str(e)}")
        return False


def get_conversation_history(session_id):
    """Get conversation history from database"""
    try:
        history = conversation_history_collection.find_one({"session_id": session_id})
        
        if history:
            history['_id'] = str(history['_id'])
            logger.info(f"✅ Found {len(history.get('conversations', []))} conversations")
            return history
        
        return {"conversations": []}
    except Exception as e:
        logger.error(f"❌ Error getting conversation history: {str(e)}")
        return {"conversations": []}


# ============== TASK OPERATIONS ==============

def create_tasks(project_id, subtasks, session_id=None):
    """Create multiple tasks from AI-generated subtasks"""
    try:
        task_ids = []
        
        for subtask in subtasks:
            task = {
                "project_id": project_id,
                "title": subtask.get("task", ""),
                "description": subtask.get("description", ""),
                "priority": subtask.get("priority", "medium"),
                "status": "pending",
                "session_id": session_id,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = tasks_collection.insert_one(task)
            task_ids.append(str(result.inserted_id))
        
        logger.info(f"✅ Created {len(task_ids)} tasks for project {project_id}")
        return task_ids
    except Exception as e:
        logger.error(f"❌ Error creating tasks: {str(e)}")
        return []


def get_project_tasks(project_id, status_filter=None):
    """Get all tasks for a project"""
    try:
        query = {"project_id": project_id}
        
        if status_filter:
            query["status"] = status_filter
        
        tasks = list(tasks_collection.find(query).sort("created_at", DESCENDING))
        
        for task in tasks:
            task['_id'] = str(task['_id'])
            task['id'] = str(task['_id'])
        
        logger.info(f"✅ Found {len(tasks)} tasks for project {project_id}")
        return tasks
    except Exception as e:
        logger.error(f"❌ Error getting tasks: {str(e)}")
        return []


def update_task(task_id, updates):
    """Update a task"""
    try:
        updates['updated_at'] = datetime.utcnow()
        
        result = tasks_collection.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": updates}
        )
        
        if result.modified_count > 0:
            logger.info(f"✅ Task {task_id} updated")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Error updating task: {str(e)}")
        return False


def delete_task(task_id):
    """Delete a task"""
    try:
        result = tasks_collection.delete_one({"_id": ObjectId(task_id)})
        
        if result.deleted_count > 0:
            logger.info(f"✅ Task {task_id} deleted")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Error deleting task: {str(e)}")
        return False


# ============== UTILITY FUNCTIONS ==============

def get_database_stats():
    """Get database statistics"""
    try:
        stats = {
            "users": users_collection.count_documents({}),
            "projects": projects_collection.count_documents({}),
            "messages": messages_collection.count_documents({}),
            "tasks": tasks_collection.count_documents({}),
            "repo_contexts": repo_context_collection.count_documents({}),
            "conversations": conversation_history_collection.count_documents({})
        }
        return stats
    except Exception as e:
        logger.error(f"❌ Error getting database stats: {str(e)}")
        return {}


logger.info("✅ Database module initialized successfully")

