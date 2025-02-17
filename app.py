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
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
import subprocess
import logging

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
system_prompt = """
# You're a programming assistant. 
## Given any task description—even if it’s vague—your job is to parse and understand the user’s intent and requirements. 
## Design the solution using a robust, efficient, and best coding practices.
## Also make sure that even if description ask for it data is never deleted anywhere on the file system as well as data outside /data is never accessed or exfiltrated.
## Please note while giving {python_dependencies} the pre-installed packages of python should not be mentioned.
## Also note that the code should be written in such a way that it can be executed in a single go.

"""
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

def resend_request(task, code, error):
    url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
    updated_task = f'''
Update this python code:
{code}
---
For below tasks:
{task}
---
Error encountered while running the task:
{error}
'''
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": updated_task            }
        ],
        "response_format": response_format
    }
    try:
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logging.error(f"Request failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Error communicating with LLM")


def code_executer(python_dependencies,python_code):
    inline_metadata_script = f"""
# /// script
# requires-python = ">=3.11"
# dependencies = [
{''.join(f"# \"{d.get('module')}\",\n" for d in python_dependencies)}# ]
# ///
""" 
    with open ("task.py", "w") as f:
        f.write(inline_metadata_script)
        f.write(python_code)    
    
    try:
        output = run(["uv","run","task.py"], capture_output=True, text=True, cwd = os.getcwd())
        std_err = output.stderr.split("\n")

        std_out = output.stdout
        exit_code = output.returncode

        for i in range(len(std_err)):
            if std_err[i].lstrip().startswith("File"):
                raise Exception(std_err[i:])
        return "success"
    except Exception as e:
        logging.info(e)
        error = str(e)
        return {"error":error}


@app.get("/")
def home():
    return "Welcome to Task Runner"

@app.post("/run")
def task_runner(task: str):
    try:
        url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Sometimes it may happen task is given in other language as well as in a different format. So, be intelligent enough to understand and write the python code to execute exactly what has been said: {task}"
                }
            ],
            "response_format": response_format
        }
        response = requests.post(url=url, headers=headers, json=data)
        response.raise_for_status()
        r = response.json()

        content = json.loads(r.get("choices")[0].get("message").get("content"))
        python_code = content.get("python_code")
        python_dependencies = content.get("python_dependencies")
        output = code_executer(python_dependencies, python_code)

        limit = 0
        while limit < 3:
            if output == "success":
                return {"message":"Task executed successfully"}
            elif output.get("error")!="":
                with open ("task.py","r") as f:
                    python_code = f.read()
                response = resend_request(task, python_code, output.get("error"))
                r = response.json()
                content = json.loads(r.get("choices")[0].get("message").get("content"))
                python_code = content.get("python_code")
                python_dependencies = content.get("python_dependencies")
                output = code_executer(python_dependencies, python_code)
                limit += 1
            else:
                raise HTTPException(status_code=500, detail="Unknown error during code execution")
            raise HTTPException(status_code=500, detail="Task failed after multiple attempts")
    except requests.RequestException:
        raise HTTPException(status_code=500, detail="Error communicating with LLM")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid task description or LLM response")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/read", response_class=PlainTextResponse)
async def read_file(path: str = Query(..., description="File path")):
    try:
        if not path.startswith("/data/") :
            raise HTTPException(status_code=400, detail="Invalid file path. Must start with /data/")


        with open(path, 'r') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
