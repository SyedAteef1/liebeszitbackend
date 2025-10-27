"""Database package"""
from app.database.mongodb import (
    init_db,
    db, users_collection, projects_collection, messages_collection,
    repo_context_collection, conversation_history_collection,
    create_or_update_user, get_user,
    create_project, get_user_projects, update_project, delete_project,
    save_message, get_project_messages,
    save_repo_context, get_repo_context, update_repo_context,
    save_conversation_history, get_conversation_history,
    get_database_stats
)

__all__ = [
    'init_db',
    'db', 'users_collection', 'projects_collection', 'messages_collection',
    'repo_context_collection', 'conversation_history_collection',
    'create_or_update_user', 'get_user',
    'create_project', 'get_user_projects', 'update_project', 'delete_project',
    'save_message', 'get_project_messages',
    'save_repo_context', 'get_repo_context', 'update_repo_context',
    'save_conversation_history', 'get_conversation_history',
    'get_database_stats'
]

