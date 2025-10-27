import os
import requests
import logging
import json
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def get_user_repos(github_token):
    """Fetch user's GitHub repositories"""
    logger.info("🔍 Fetching user repositories...")
    
    headers = {'Authorization': f'token {github_token}'}
    url = "https://api.github.com/user/repos?per_page=100&sort=updated"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        repos = [{
            'name': r['name'],
            'full_name': r['full_name'],
            'url': r['html_url'],
            'description': r['description'],
            'language': r['language'],
            'updated_at': r['updated_at']
        } for r in data if isinstance(data, list)]
        
        logger.info(f"✅ Found {len(repos)} repositories")
        return repos
    except Exception as e:
        logger.error(f"❌ Error fetching repos: {str(e)}")
        raise

def analyze_repo_structure(owner, repo, github_token):
    """Get detailed repo structure and generate AI summary"""
    logger.info(f"📦 Analyzing {owner}/{repo}...")
    
    headers = {'Authorization': f'token {github_token}'}
    
    try:
        # Get repo tree
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
        tree_resp = requests.get(tree_url, headers=headers, timeout=10)
        
        if tree_resp.status_code != 200:
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1"
            tree_resp = requests.get(tree_url, headers=headers, timeout=10)
        
        tree_data = tree_resp.json()
        all_files = [f['path'] for f in tree_data.get('tree', []) if f['type'] == 'blob']
        
        # Build folder structure
        folders = {}
        for file in all_files:
            parts = file.split('/')
            if len(parts) > 1:
                folder = parts[0]
                folders[folder] = folders.get(folder, 0) + 1
        
        # Get README
        readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        readme_resp = requests.get(readme_url, headers=headers, timeout=10)
        readme = ""
        if readme_resp.status_code == 200:
            import base64
            readme = base64.b64decode(readme_resp.json()['content']).decode('utf-8')[:3000]
        
        # Generate AI summary
        prompt = f"""Analyze this GitHub repository structure and provide a detailed summary.

Repository: {owner}/{repo}
Total Files: {len(all_files)}
Main Folders: {', '.join(list(folders.keys())[:20])}
Key Files: {', '.join([f for f in all_files if any(x in f for x in ['package.json', 'requirements.txt', 'README', 'Dockerfile', '.env'])][:10])}

README Content:
{readme[:1500]}

Provide JSON:
{{
  "project_name": "Project name",
  "description": "Detailed description",
  "tech_stack": ["Tech 1", "Tech 2"],
  "main_features": ["Feature 1", "Feature 2"],
  "architecture": "Architecture overview",
  "folder_structure": {{
    "folder_name": "Purpose of this folder"
  }}
}}"""
        
        logger.info("🤖 Calling Gemini for analysis...")
        api_url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent'
        response = requests.post(
            api_url,
            headers={'Content-Type': 'application/json'},
            params={'key': GEMINI_API_KEY},
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 2048}
            },
            timeout=25
        )
        
        data = response.json()
        
        if 'candidates' in data and data['candidates']:
            text = data['candidates'][0]['content']['parts'][0]['text']
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                result = json.loads(json_match.group())
                result['total_files'] = len(all_files)
                result['folders'] = folders
                logger.info("✅ Analysis complete")
                return result
        
        raise Exception("Failed to parse Gemini response")
        
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise
