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
# You're a programming assistant. Make sure all the given points are covered in the code:
- Given any task description—even if it’s vague—your job is to parse and understand the user’s intent and requirements.
- Make sure to get all the permission for reading, writing, deleting, updating files and folders as per the task is given.
- Design the solution using a robust, efficient, and best coding practices.
- Also make sure that even if description ask for it data is never deleted anywhere on the file system as well as data outside /data is never accessed or exfiltrated.
- Ensure that the pre-installed packages/modules/libraries of python should not be mentioned in the dependencies for example subprocess, requests, json, os, logging, etc.
- Also note that the code should be written in such a way that it can be executed in a single go.
- We're using Ubuntu on WSL for this task. We'll run this system on Docker where uv is already installed.
- For handling filepaths use relevant libraries and functions as per our current system which is Ubuntu.
    - For example, csv_file_path = Path('data/student_records.csv') should be used instead of csv_file_path = Path('/data/student_records.csv') for defining the path.
- Make sure to handle all the errors that might occur during the execution of the code.
- Note there will be many vague taks, so you have to do something like this on your own. Example of such cases: Task is to "Run a SQL query on a SQLite or DuckDB database", you can do the following:
    - Create a SQLite or DuckDB database file with some dummy data.
    - Run the SQL query on the database.
    - Print the output of the query.
    - Similarly, you can do for other tasks as well.
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
        output = subprocess.run(["uv","run","task.py"], capture_output=True, text=True)
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
        if not AIPROXY_TOKEN:
            logging.error("AIPROXY_TOKEN environment variable is not set")
            raise HTTPException(status_code=500, detail="API token is not configured")

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
        
        logging.info(f"Sending request to LLM API: {url}")
        response = requests.post(
            url=url,
            headers=headers,
            json=data,
            timeout=20  # 20 second timeout
        )
        response.raise_for_status()
        r = response.json()
        logging.info(f"Received response from LLM API: {r}")

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
            logging.error(f"Task failed after {limit} attempts")
            raise HTTPException(status_code=500, detail=f"Task failed after {limit} attempts. Last error: {output.get('error', 'Unknown error')}")
    except requests.Timeout:
        logging.error("LLM API request timed out")
        raise HTTPException(status_code=504, detail="LLM API request timed out")
    except requests.RequestException as e:
        logging.error(f"LLM API request failed: {str(e)}")
        raise HTTPException(status_code=502, detail=f"LLM API communication error: {str(e)}")
    except json.JSONDecodeError:
        logging.error("Invalid JSON response from LLM API")
        raise HTTPException(status_code=502, detail="Invalid response from LLM API")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/read")
async def read_file(path: str = Query(..., description="File path")):
    try:
        # Validate path format
        if not path.startswith('/data'):
            logging.error(f"Invalid file path: {path}")
            raise HTTPException(status_code=400, detail="File path must start with /data/")
        
        # Convert path to absolute if needed
        abs_path = os.path.abspath(path)
        
        # Check if file exists
        if not os.path.exists(abs_path):
            logging.error(f"File not found: {abs_path}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Verify it's a file
        if not os.path.isfile(abs_path):
            logging.error(f"Path is not a file: {abs_path}")
            raise HTTPException(status_code=400, detail="Path must be a file")
            
        # Read file content
        with open(abs_path, 'r') as file:
            content = file.read()
        return content
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error reading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
