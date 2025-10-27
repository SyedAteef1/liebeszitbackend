import os
import requests
import logging
import json
import re
from datetime import datetime
from app.database.mongodb import (
    save_repo_context, get_repo_context, update_repo_context,
    save_conversation_history, get_conversation_history as db_get_conversation_history
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Store sessions in memory (use Redis in production)
task_sessions = {}

def add_to_history(session_id, prompt, analysis=None, plan=None):
    """Add a prompt and its results to conversation history (database)"""
    try:
        save_conversation_history(session_id, prompt, analysis, plan)
        logger.info(f"💾 Added to database history for session {session_id}")
    except Exception as e:
        logger.error(f"❌ Error saving to history: {str(e)}")

def get_conversation_history(session_id):
    """Retrieve conversation history for a session (from database)"""
    try:
        return db_get_conversation_history(session_id)
    except Exception as e:
        logger.error(f"❌ Error getting history: {str(e)}")
        return {'conversations': []}

def parse_json_from_text(text, context="response"):
    """Extract and parse JSON from text with error recovery"""
    try:
        # Try to find JSON in the text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            logger.error(f"❌ Could not find JSON in {context}")
            raise Exception(f"No JSON found in {context}")
        
        json_str = json_match.group()
        logger.info(f"📝 Extracted JSON ({len(json_str)} chars)")
        
        # Try to parse the JSON
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON Parse Error at position {e.pos}: {e.msg}")
            logger.error(f"📄 Problematic JSON snippet: ...{json_str[max(0, e.pos-100):min(len(json_str), e.pos+100)]}...")
            
            # Try to fix common JSON errors
            # Remove trailing commas before } or ]
            fixed_json = re.sub(r',(\s*[}\]])', r'\1', json_str)
            # Remove comments if any
            fixed_json = re.sub(r'//.*?\n', '\n', fixed_json)
            fixed_json = re.sub(r'/\*.*?\*/', '', fixed_json, flags=re.DOTALL)
            
            try:
                logger.info("🔧 Attempting to fix JSON errors...")
                return json.loads(fixed_json)
            except json.JSONDecodeError as e2:
                logger.error(f"❌ Could not fix JSON automatically")
                logger.error(f"📄 Full malformed JSON:\n{json_str[:1000]}...")
                raise Exception(f"Invalid JSON in {context}: {e.msg} at position {e.pos}")
    except Exception as e:
        logger.error(f"❌ JSON extraction failed: {str(e)}")
        raise

def search_codebase_for_keywords(owner, repo, keywords, github_token=None):
    """Search GitHub repository for specific keywords"""
    logger.info(f"🔍 Searching codebase for: {keywords}")
    
    try:
        headers = {'Authorization': f'token {github_token}'} if github_token else {}
        search_results = []
        
        for keyword in keywords[:3]:  # Limit to 3 keywords
            search_url = f"https://api.github.com/search/code?q={keyword}+repo:{owner}/{repo}"
            resp = requests.get(search_url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items', [])[:5]
                for item in items:
                    search_results.append({
                        'file': item['path'],
                        'keyword': keyword,
                        'url': item['html_url']
                    })
                logger.info(f"✅ Found {len(items)} files with '{keyword}'")
            else:
                logger.warning(f"⚠️ Search failed for '{keyword}': {resp.status_code}")
        
        return search_results
    except Exception as e:
        logger.error(f"❌ Codebase search error: {str(e)}")
        return []

def analyze_task_with_llm(task, session_id=None, repo_context=None, owner=None, repo=None, github_token=None):
    """Phase 1: Intelligent task analysis with deep project context"""
    logger.info("="*60)
    logger.info("STEP 1: INTELLIGENT TASK ANALYSIS WITH PROJECT CONTEXT")
    logger.info("="*60)
    logger.info(f"📝 Input Task: {task}")
    logger.info(f"🔑 Session ID: {session_id}")
    
    # Build context text with deep project understanding
    context_text = ""
    if repo_context:
        modules_text = ""
        if repo_context.get('key_modules'):
            modules_text = "\n\nKey Modules:\n" + "\n".join(
                [f"- {m['module_name']}: {m['description']}" for m in repo_context['key_modules'][:5]]
            )
        
        context_text = f"""
**Project Context:**
- Summary: {repo_context.get('project_summary', 'N/A')}
- Architecture: {repo_context.get('architecture_overview', 'N/A')}
- Tech Stack: {repo_context.get('tech_stack', {}).get('language', 'N/A')}, {repo_context.get('tech_stack', {}).get('framework_backend', 'N/A')}
{modules_text}
"""
    
    # Step 1: Detect task type with project context
    logger.info("🔍 Step 1A: Detecting task type with project context...")
    
    type_detection_prompt = f"""Analyze this task with full project context.

{context_text}

Task: "{task}"

Task: "{task}"

Determine:
1. Is this adding a NEW feature that doesn't exist?
2. Is this UPDATING/MODIFYING an existing feature?
3. Is it BOTH (adding new + modifying existing)?

Extract keywords that might exist in the codebase (e.g., "dashboard", "payment", "login").

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no extra text.
Do not use trailing commas. Ensure all strings are properly quoted.

Respond with valid JSON:
{{
  "task_type": "new" | "update" | "both",
  "keywords": ["keyword1", "keyword2"],
  "reasoning": "Brief explanation"
}}"""
    
    try:
        api_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent'
        
        # Detect task type
        logger.info("🚀 Calling Gemini for task type detection...")
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': type_detection_prompt}]}],
                'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 512}
            },
            timeout=60
        )
        
        data = response.json()
        
        # Check for errors in response
        if 'error' in data:
            error_msg = data['error'].get('message', 'Unknown error')
            logger.error(f"❌ Gemini API Error: {error_msg}")
            raise Exception(f"Gemini API error: {error_msg}")
        
        # Check if candidates exist
        if 'candidates' not in data or not data['candidates']:
            logger.error(f"❌ No candidates in response. Full response: {json.dumps(data)}")
            if 'promptFeedback' in data:
                feedback = data['promptFeedback']
                logger.error(f"⚠️ Prompt Feedback: {json.dumps(feedback)}")
            raise Exception("Gemini API returned no candidates")
        
        text = data['candidates'][0]['content']['parts'][0]['text']
        logger.info(f"📝 Task Type Response: {text[:500]}...")
        
        task_type_info = parse_json_from_text(text, "task type detection")
        
        logger.info(f"✅ Task Type: {task_type_info['task_type']}")
        logger.info(f"🔑 Keywords: {task_type_info['keywords']}")
        logger.info(f"💡 Reasoning: {task_type_info['reasoning']}")
        
        # Step 2: Search codebase if updating existing features
        codebase_findings = []
        if task_type_info['task_type'] in ['update', 'both'] and owner and repo:
            logger.info("🔍 Step 1B: Searching codebase for existing features...")
            codebase_findings = search_codebase_for_keywords(
                owner, repo, task_type_info['keywords'], github_token
            )
            
            if not codebase_findings:
                logger.warning("⚠️ No existing code found for keywords!")
                logger.info("💡 This might be a NEW feature, not an update")
        
        # Step 3: Determine if we need clarification
        logger.info("🔍 Step 1C: Checking if clarification needed...")
        
        context_text = ""
        if repo_context:
            context_text = f"""
Repository Info:
- Files: {', '.join(repo_context.get('files', [])[:15])}
- Tech Stack: {', '.join(repo_context.get('tech_stack', []))}
"""
        
        findings_text = ""
        if codebase_findings:
            findings_text = "\n\nExisting Code Found:\n" + "\n".join(
                [f"- {f['file']} (contains '{f['keyword']}')" for f in codebase_findings[:5]]
            )
        elif task_type_info['task_type'] in ['update', 'both']:
            findings_text = "\n\n⚠️ WARNING: Task mentions updating existing features, but NO related code was found in the repository!"
        
        clarity_prompt = f"""Analyze if this task is clear enough to implement.

{context_text}

Task: "{task}"
Task Type: {task_type_info['task_type']}
{findings_text}

Rules:
1. If task type is "update" or "both" but NO existing code found → Ask questions about what exists
2. If task is vague (e.g., "get dashboard ready") → Ask specific questions
3. If task is clear and specific → Mark as clear

When asking questions, provide a helpful explanation for WHY each question matters.

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no extra text.
Do not use trailing commas. Ensure all strings are properly quoted.

Respond with valid JSON in this format:
{{"status": "clear", "analysis": "Task is clear"}}
OR
{{
  "status": "ambiguous", 
  "questions": [
    {{
      "question": "What specific AI model should be used?",
      "explanation": "Different AI models have different capabilities and costs. This helps us choose the right tool for your needs."
    }}
  ]
}}"""
        
        logger.info("🚀 Calling Gemini for clarity analysis...")
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': clarity_prompt}]}],
                'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 512}
            },
            timeout=60
        )
        
        data = response.json()
        logger.info(f"📦 Gemini Response: {json.dumps(data, indent=2)}")
        
        # Check for errors in response
        if 'error' in data:
            error_msg = data['error'].get('message', 'Unknown error')
            logger.error(f"❌ Gemini API Error: {error_msg}")
            raise Exception(f"Gemini API error: {error_msg}")
        
        # Check if candidates exist
        if 'candidates' not in data or not data['candidates']:
            logger.error(f"❌ No candidates in response. Full response: {json.dumps(data)}")
            # Check for safety filters or other issues
            if 'promptFeedback' in data:
                feedback = data['promptFeedback']
                logger.error(f"⚠️ Prompt Feedback: {json.dumps(feedback)}")
                if 'blockReason' in feedback:
                    raise Exception(f"Content blocked by safety filters: {feedback['blockReason']}")
            raise Exception("Gemini API returned no candidates. This might be due to safety filters or API issues.")
        
        text = data['candidates'][0]['content']['parts'][0]['text']
        logger.info(f"📝 Clarity Analysis Response: {text[:500]}...")
        
        result = parse_json_from_text(text, "clarity analysis")
        
        # Add task type info to result
        result['task_type'] = task_type_info['task_type']
        result['keywords'] = task_type_info['keywords']
        result['codebase_findings'] = codebase_findings
        
        logger.info(f"✨ Final Analysis: {json.dumps(result, indent=2)}")
        
        if session_id:
            task_sessions[session_id] = {
                'task': task,
                'analysis': result,
                'created_at': datetime.utcnow()
            }
            logger.info(f"💾 Session stored: {session_id}")
            
            # Add to conversation history
            add_to_history(session_id, task, analysis=result)
        
        logger.info("="*60)
        logger.info(f"✅ ANALYSIS COMPLETE - Status: {result.get('status')}")
        logger.info("="*60)
        return result
            
    except Exception as e:
        logger.error(f"❌ LLM Analysis Error: {str(e)}")
        logger.exception("Full traceback:")
        raise Exception(f"Gemini API failed: {str(e)}")

def create_deep_project_context(owner, repo, github_token=None):
    """Deep analysis of repository to create comprehensive project context"""
    logger.info("="*60)
    logger.info("🧠 DEEP PROJECT CONTEXT ANALYSIS")
    logger.info("="*60)
    
    repo_full_name = f"{owner}/{repo}"
    logger.info(f"📦 Repository: {repo_full_name}")
    
    # ✨ CHECK DATABASE CACHE FIRST
    cached_context = get_repo_context(repo_full_name)
    if cached_context:
        logger.info(f"⚡ Using cached repo context (accessed {cached_context.get('access_count', 0)} times)")
        logger.info(f"📅 Cache age: {cached_context.get('updated_at', 'unknown')}")
        return cached_context['context_text']
    
    logger.info("🔄 Cache miss - performing fresh analysis...")
    
    try:
        headers = {'Authorization': f'token {github_token}'} if github_token else {}
        
        # Fetch complete file tree
        logger.info("🔍 Fetching complete file tree...")
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
        tree_resp = requests.get(tree_url, headers=headers, timeout=60)
        
        if tree_resp.status_code != 200:
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1"
            tree_resp = requests.get(tree_url, headers=headers, timeout=15)
        
        tree_data = tree_resp.json()
        all_files = [f['path'] for f in tree_data.get('tree', []) if f['type'] == 'blob']
        logger.info(f"📂 Found {len(all_files)} files")
        
        # Fetch README
        logger.info("📄 Fetching README...")
        readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        readme_resp = requests.get(readme_url, headers=headers, timeout=10)
        readme_content = ""
        if readme_resp.status_code == 200:
            import base64
            readme_content = base64.b64decode(readme_resp.json()['content']).decode('utf-8')[:3000]
            logger.info("✅ README fetched")
        
        # Deep analysis prompt
        file_list_str = ", ".join(all_files[:100])  # First 100 files
        
        prompt = f"""You are a 10x Senior Solutions Architect. Perform a deep analysis of this GitHub repository to create a comprehensive "Project Context" summary.

**Repository Information:**
---
**File Tree:**
{file_list_str}

**README.md:**
{readme_content}
---

Analyze and generate a JSON object with:

1. `project_summary`: One-paragraph description of the project's purpose
2. `tech_stack`: Object with keys: `language`, `framework_backend`, `framework_frontend`, `database`, `key_libraries`
3. `architecture_overview`: Brief architecture description (e.g., "Monolithic MVC", "Microservices")
4. `key_modules`: Array of core features/modules. For each:
   - `module_name`: Name of the module
   - `description`: What this module does
   - `relevant_files`: Top 3-5 most important file paths for this module

Do not guess. Prioritize accuracy.

Respond ONLY with valid JSON:
{{
  "project_summary": "...",
  "tech_stack": {{
    "language": "...",
    "framework_backend": "...",
    "framework_frontend": "...",
    "database": "...",
    "key_libraries": ["..."]
  }},
  "architecture_overview": "...",
  "key_modules": [
    {{
      "module_name": "...",
      "description": "...",
      "relevant_files": ["..."]
    }}
  ]
}}"""
        
        logger.info("🚀 Calling Gemini for deep analysis...")
        api_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent'
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 4096}
            },
            timeout=30
        )
        
        data = response.json()
        logger.info(f"📦 Gemini Response Keys: {list(data.keys())}")
        
        # Check for errors in response
        if 'error' in data:
            error_msg = data['error'].get('message', 'Unknown error')
            logger.error(f"❌ Gemini API Error: {error_msg}")
            raise Exception(f"Gemini API error: {error_msg}")
        
        # Check if candidates exist
        if 'candidates' not in data or not data['candidates']:
            logger.error(f"❌ No candidates in deep analysis response: {json.dumps(data)}")
            if 'promptFeedback' in data:
                feedback = data['promptFeedback']
                logger.error(f"⚠️ Prompt Feedback: {json.dumps(feedback)}")
            raise Exception("Gemini API returned no candidates for deep analysis")
        
        text = data['candidates'][0]['content']['parts'][0]['text']
        logger.info(f"📝 Deep Analysis Response: {text[:500]}...")
        
        project_context = parse_json_from_text(text, "deep analysis")
        logger.info("✅ Deep analysis complete!")
        logger.info(f"📊 Found {len(project_context.get('key_modules', []))} key modules")
        
        # ✨ SAVE TO DATABASE CACHE
        try:
            language = project_context.get('tech_stack', {}).get('language', 'Unknown')
            metadata = {
                'file_count': len(all_files),
                'has_readme': bool(readme_content),
                'tech_stack': project_context.get('tech_stack', {})
            }
            save_repo_context(repo_full_name, project_context, language, metadata)
            logger.info(f"💾 Repo context saved to database for future use")
        except Exception as save_error:
            logger.error(f"⚠️ Failed to save repo context (non-critical): {str(save_error)}")
        
        return project_context
        
    except Exception as e:
        logger.error(f"❌ Deep Analysis Error: {str(e)}")
        logger.exception("Full traceback:")
        raise Exception(f"Deep analysis failed: {str(e)}")

def analyze_github_repo(repo_url, github_token=None):
    """Analyze GitHub repository - wrapper for backward compatibility"""
    parts = repo_url.rstrip('/').split('/')
    owner, repo = parts[-2], parts[-1]
    return create_deep_project_context(owner, repo, github_token)

def generate_implementation_plan(task, answers=None, session_id=None, team_members=None):
    """Phase 2: Generate detailed implementation plan based on task type and codebase findings"""
    logger.info("="*60)
    logger.info("STEP 2: IMPLEMENTATION PLAN GENERATION")
    logger.info("="*60)
    logger.info(f"📝 Task: {task}")
    logger.info(f"💬 Answers: {answers}")
    logger.info(f"🔑 Session ID: {session_id}")
    
    # Get task analysis from session
    task_type = "new"
    codebase_findings = []
    if session_id and session_id in task_sessions:
        session = task_sessions[session_id]
        analysis = session.get('analysis', {})
        task_type = analysis.get('task_type', 'new')
        codebase_findings = analysis.get('codebase_findings', [])
        logger.info(f"📂 Task Type: {task_type}")
        logger.info(f"🔍 Codebase Findings: {len(codebase_findings)} files")
    
    answers_text = ""
    if answers:
        answers_text = "\n".join([f"- {k}: {v}" for k, v in answers.items()])
        logger.info(f"📋 Clarifications:\n{answers_text}")
    
    findings_text = ""
    if codebase_findings:
        findings_text = "\n\nExisting Code to Modify:\n" + "\n".join(
            [f"- {f['file']}" for f in codebase_findings[:5]]
        )
    
    prompt = f"""You are a senior project manager. Create a detailed implementation plan.

Task: "{task}"
Task Type: {task_type.upper()}
{f"\nClarifications:\n{answers_text}" if answers_text else ""}
{findings_text}

Instructions:
- If task type is "new": Create plan for building from scratch
- If task type is "update": Focus on modifying existing code in the files listed
- If task type is "both": Plan for both new features and modifications

Create 5-7 specific subtasks with:
- Clear, actionable title
- Detailed description
- Suggested role (Frontend Dev, Backend Dev, Designer, etc.)
- Realistic deadline (Day 1, Day 2, etc.)
- Expected output/deliverable
- Clarity score (0-100)

Return ONLY valid JSON:
{{
  "main_task": "Task Title",
  "goal": "What we're achieving",
  "task_type": "{task_type}",
  "subtasks": [
    {{
      "title": "Subtask name",
      "description": "Detailed steps",
      "assigned_to": "Role",
      "deadline": "Day X",
      "output": "Deliverable",
      "clarity_score": 95
    }}
  ]
}}"""

    try:
        logger.info("🚀 Calling Gemini API for implementation plan...")
        api_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent'
        
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'temperature': 0.6, 'maxOutputTokens': 2048}
            },
            timeout=20
        )
        
        data = response.json()
        logger.info(f"✅ Gemini Response Status: {response.status_code}")
        logger.info(f"📦 Response Keys: {list(data.keys())}")
        
        # Check for errors in response
        if 'error' in data:
            error_msg = data['error'].get('message', 'Unknown error')
            logger.error(f"❌ Gemini API Error: {error_msg}")
            raise Exception(f"Gemini API error: {error_msg}")
        
        # Check if candidates exist
        if 'candidates' not in data or not data.get('candidates'):
            logger.error(f"❌ No candidates in plan generation response: {json.dumps(data)}")
            if 'promptFeedback' in data:
                feedback = data['promptFeedback']
                logger.error(f"⚠️ Prompt Feedback: {json.dumps(feedback)}")
                if 'blockReason' in feedback:
                    raise Exception(f"Content blocked: {feedback['blockReason']}")
            raise Exception("Gemini API returned no candidates for plan generation")
        
        text = data['candidates'][0]['content']['parts'][0]['text']
        logger.info(f"📝 Plan Response Preview: {text[:200]}...")
        
        result = parse_json_from_text(text, "plan generation")
        logger.info(f"✨ Plan Generated: {len(result.get('subtasks', []))} subtasks")
        logger.info("="*60)
        logger.info(f"✅ PLAN COMPLETE")
        logger.info("="*60)
        
        # Add plan to conversation history in database
        if session_id:
            try:
                # Save to database with plan included
                save_conversation_history(session_id, task, analysis=None, plan=result)
                logger.info(f"💾 Added plan to database history")
            except Exception as e:
                logger.error(f"❌ Error saving plan to history: {str(e)}")
        
        return result
            
    except Exception as e:
        logger.error(f"❌ Plan Generation Error: {str(e)}")
        raise Exception(f"Gemini API failed: {str(e)}")


def summarize_slack_messages(messages):
    """
    Generate AI-powered summary of Slack channel messages
    
    Args:
        messages: List of message objects with 'user', 'text', 'timestamp'
    
    Returns:
        dict: Summary with key_updates, active_users, blockers, overall_status
    """
    logger.info("="*60)
    logger.info("SLACK CHANNEL SUMMARIZATION")
    logger.info("="*60)
    logger.info(f"📊 Analyzing {len(messages)} messages")
    
    try:
        # Prepare messages for AI
        conversation_text = ""
        for msg in messages:
            user = msg.get('user', 'Unknown')
            text = msg.get('text', '')
            conversation_text += f"{user}: {text}\n"
        
        prompt = f"""Analyze the following Slack channel conversation and provide a concise summary.

SLACK MESSAGES:
{conversation_text}

Generate a JSON response with this structure:
{{
  "key_updates": [
    {{"user": "User Name", "update": "Brief description of what they said/did"}},
    ...
  ],
  "active_users": ["List of users who participated"],
  "blockers": ["Any blockers or issues mentioned"],
  "progress_indicators": ["Any progress updates or completed tasks"],
  "overall_status": "A one-sentence summary of the channel activity",
  "sentiment": "positive/neutral/negative",
  "action_items": ["Any action items or next steps mentioned"]
}}

Keep updates brief (max 15 words each). Return ONLY valid JSON, no markdown, no code blocks."""
        
        logger.info("🚀 Calling Gemini API for summary...")
        api_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent'
        
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': 0.3,
                    'topK': 40,
                    'topP': 0.95,
                    'maxOutputTokens': 2048
                }
            },
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Gemini API returned status {response.status_code}")
        
        response_data = response.json()
        
        if 'candidates' not in response_data:
            raise Exception("No candidates in Gemini response")
        
        text = response_data['candidates'][0]['content']['parts'][0]['text']
        logger.info(f"📝 Summary Response Preview: {text[:200]}...")
        
        result = parse_json_from_text(text, "slack summary")
        logger.info(f"✨ Summary Generated Successfully")
        logger.info("="*60)
        
        return result
            
    except Exception as e:
        logger.error(f"❌ Summary Generation Error: {str(e)}")
        # Return a fallback summary
        return {
            "key_updates": [],
            "active_users": list(set([msg.get('user', 'Unknown') for msg in messages])),
            "blockers": [],
            "progress_indicators": [],
            "overall_status": f"Channel has {len(messages)} recent messages",
            "sentiment": "neutral",
            "action_items": [],
            "error": str(e)
        }
