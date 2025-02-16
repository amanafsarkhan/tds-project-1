# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
#   "fastapi",
#   "uvicorn"
# ]
# ///

import requests
import os
import json
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
AIPROXY_TOKEN = os.environ.get("AIPROXY_TOKEN")
headers = {
        "Authorization": f"Bearer {AIPROXY_TOKEN}",
        "Content-Type": "application/json"
    }

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "task_runner",
        "schema": {
            "type": "object",
            "required": ["python_dependencies", "python_code"],
            "properties": {
                "python_code": {
                    "type": "string",
                    "description": "Python code to execute"
                },
                "python_dependencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "module": {
                                "type": "string",
                                "description": "List of python dependencies to install"
                            }
                        },
                        "required": ["module"],
                        'additionalProperties': False
                    }
                }
            }
        }
    }
}

@app.get("/")
def home():
    return "Welcome to Task Runner"

@app.post("/run")
def task_runner(task: str):
    url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "You're an expert and advanced AI Agent to write python code for the given task. Sometimes you may encounter task is not well-defined then you have to manage it like a pro."  
            },
            {
                "role": "user",
                "content": f"Understand the given task description and write the python code to execute exactly what has been said: {task}"
            }
        ],
        "response_format": response_format
    }
    response = requests.post(url=url, headers=headers, json=data)
    r = response.json()
    content = json.loads(r.get("choices")[0].get("message").get("content"))

    dependencies = content.get("python_dependencies")
    inline_metadata_script = f"""
# /// script
# requires-python = ">=3.11"
# dependencies = [
{''.join(f"# \"{d.get('module')}\",\n" for d in dependencies)}# ]
"""

    with open ("task.py", "w") as f:
        f.write(inline_metadata_script)
        f.write(content.get("python_code"))    
    return r

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)
