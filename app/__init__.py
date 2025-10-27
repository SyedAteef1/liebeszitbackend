"""
Feeta Backend Application Factory
Clean, modular Flask application
"""
import logging
from flask import Flask
from flask_cors import CORS
from app.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    """Application factory pattern"""
    
    logger.info("="*80)
    logger.info("🚀 Initializing Feeta Backend")
    logger.info("="*80)
    
    # Create Flask app
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY  # Required for session
    
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"❌ Configuration Error: {e}")
        raise
    
    # Setup CORS
    CORS(app, 
         supports_credentials=True,
         origins=['http://localhost:3000', 'https://localhost:3000', 'http://127.0.0.1:3000'],
         allow_headers=['Content-Type', 'Authorization'])
    
    logger.info(f"✅ CORS enabled for: {Config.FRONTEND_URL}")
    
    # Initialize database
    from app.database.mongodb import init_db
    init_db()
    logger.info("✅ Database initialized")
    
    # Register API blueprints
    from app.api.auth import auth_bp
    from app.api.projects import project_bp
    from app.api.tasks import task_bp
    from app.api.github import github_bp
    from app.api.slack import slack_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(project_bp, url_prefix='/api')
    app.register_blueprint(task_bp, url_prefix='/api')
    app.register_blueprint(github_bp, url_prefix='/github')
    app.register_blueprint(slack_bp, url_prefix='/slack')
    
    logger.info("✅ API routes registered")
    
    # Health check endpoint
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'service': 'feeta-backend'}, 200
    
    logger.info("="*80)
    logger.info("✨ Feeta Backend Ready!")
    logger.info(f"🌐 Running on: {Config.BACKEND_URL}")
    logger.info("="*80)
    
    return app

