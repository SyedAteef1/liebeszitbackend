# Feeta Backend

Clean, modular Flask backend for the Feeta AI Task Management platform.

## 📁 Project Structure

```
backend/
├── app/
│   ├── __init__.py          # Application factory
│   ├── config.py            # Configuration management
│   ├── api/                 # API route blueprints
│   │   ├── auth.py          # Authentication routes
│   │   ├── projects.py      # Project CRUD operations
│   │   ├── tasks.py         # Task analysis routes
│   │   ├── github.py        # GitHub OAuth & API
│   │   └── slack.py         # Slack OAuth & messaging
│   ├── services/            # Business logic layer
│   │   ├── ai_service.py    # Gemini AI integration
│   │   └── github_service.py # GitHub API utilities
│   ├── database/            # Database layer
│   │   └── mongodb.py       # MongoDB operations
│   └── utils/               # Utility functions
├── run.py                   # Application entry point
├── requirements.txt         # Python dependencies
└── .env                     # Environment variables (create from .env.example)
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Slack
SLACK_CLIENT_ID=your_slack_client_id
SLACK_CLIENT_SECRET=your_slack_client_secret

# URLs
BASE_URL=https://localhost:5000
FRONTEND_URL=http://localhost:3000

# Flask
FLASK_SECRET=your_secret_key

# MongoDB
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/

# GitHub
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Gemini AI
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Run the Server

```bash
python run.py
```

The server will start on `https://localhost:5000` with a self-signed SSL certificate.

## 🔑 API Endpoints

### Authentication
- `POST /auth/register` - User registration
- `POST /auth/login` - User login
- `GET /auth/me` - Get current user

### Projects
- `GET /api/projects` - Get all projects
- `POST /api/projects` - Create project
- `PUT /api/projects/:id` - Update project
- `DELETE /api/projects/:id` - Delete project
- `GET /api/projects/:id/messages` - Get project messages
- `POST /api/projects/:id/messages` - Add message

### Tasks (AI)
- `POST /api/analyze` - Analyze task with AI
- `POST /api/generate_plan` - Generate implementation plan
- `GET /api/conversation_history/:session_id` - Get history

### GitHub
- `GET /github/install` - Start OAuth flow
- `GET /github/callback` - OAuth callback
- `GET /github/api/repos` - Get user repositories
- `GET /github/api/check_connection` - Check if connected

### Slack
- `GET /slack/install` - Start OAuth flow
- `GET /slack/oauth_redirect` - OAuth callback
- `GET /slack/api/list_conversations` - List channels
- `POST /slack/api/send_message` - Send message

### Health Check
- `GET /health` - Server health status

## 🗄️ Database Collections

### MongoDB Collections:
- **users** - User accounts and OAuth tokens
- **projects** - User projects
- **messages** - Chat messages per project
- **repo_contexts** - Cached GitHub repository analysis
- **conversation_history** - AI conversation history
- **slack_tokens** - Slack OAuth tokens

## 🛠️ Development

### Adding New API Routes

1. Create a new file in `app/api/`:
```python
from flask import Blueprint, request, jsonify

my_bp = Blueprint('my_feature', __name__)

@my_bp.route("/api/my_endpoint")
def my_endpoint():
    return jsonify({"message": "Hello"})
```

2. Register in `app/__init__.py`:
```python
from app.api.my_feature import my_bp
app.register_blueprint(my_bp)
```

### Adding New Services

1. Create a file in `app/services/`:
```python
# app/services/my_service.py
def my_function():
    return "result"
```

2. Import in your routes:
```python
from app.services.my_service import my_function
```

## 📝 Logging

All routes and services use Python's logging module:

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Info message")
logger.error("Error message")
```

## 🔒 Security Notes

- **SSL Certificate**: Uses self-signed certificate for development (change for production)
- **Environment Variables**: Never commit `.env` file
- **MongoDB**: Use connection string with authentication
- **OAuth Secrets**: Keep client secrets secure

## 🚀 Production Deployment

For production, use a proper WSGI server:

```bash
pip install gunicorn

gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

## 📚 Dependencies

- **Flask** - Web framework
- **flask-cors** - CORS support
- **pymongo** - MongoDB driver
- **python-dotenv** - Environment variables
- **requests** - HTTP client
- **PyJWT** - JWT tokens
- **pyOpenSSL** - SSL support

## 🐛 Troubleshooting

### ModuleNotFoundError
```bash
# Make sure you're in the backend directory
cd backend

# Reinstall dependencies
pip install -r requirements.txt
```

### SSL Certificate Warning
- This is normal for development with self-signed certificates
- Click "Advanced" → "Proceed to localhost" in your browser

### MongoDB Connection Error
- Verify your `MONGO_URI` in `.env`
- Check if your IP is whitelisted in MongoDB Atlas

## 📖 Learn More

- [Flask Documentation](https://flask.palletsprojects.com/)
- [MongoDB Python Driver](https://pymongo.readthedocs.io/)
- [Google Gemini API](https://ai.google.dev/docs)
