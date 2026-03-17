# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp",
#     "httpx",
# ]
# ///

import os
import httpx
from mcp.server.fastmcp import FastMCP

# This file implements the open-source MCP proxy server for Mdtero.
# It can be used by Claude Code, Cursor, or OpenClaw.
# Users must provide MDTERO_API_KEY environment variable.

BASE_URL = os.environ.get("MDTERO_API_URL", "https://api.mdtero.com")
API_KEY = os.environ.get("MDTERO_API_KEY")

mcp = FastMCP("Mdtero", dependencies=["httpx"])

@mcp.tool()
async def parse_paper(url_or_doi: str, elsevier_api_key: str = None) -> str:
    """
    Parse a scientific paper (Elsevier DOI or URL) into a clean Markdown bundle.

    Args:
        url_or_doi: The DOI or URL of the paper to parse.
        elsevier_api_key: Optional Elsevier API key for full text access if applicable.
    """
    if not API_KEY:
        return "Error: MDTERO_API_KEY environment variable is not set. Please generate one at https://mdtero.com/account"

    async with httpx.AsyncClient() as client:
        try:
            payload = {"input": url_or_doi}
            if elsevier_api_key:
                payload["elsevier_api_key"] = elsevier_api_key

            response = await client.post(
                f"{BASE_URL}/tasks/parse",
                headers={"ApiKey": API_KEY},
                json=payload,
                timeout=60.0
            )
            if response.status_code == 200:
                data = response.json()
                task_id = data.get("task_id")
                return f"Successfully initiated parse task. Task ID: {task_id}\nCheck your Mdtero dashboard to download the parsed artifacts."
            else:
                return f"Failed to parse paper: {response.text}"
        except Exception as e:
            return f"Error connecting to Mdtero API: {str(e)}"

@mcp.tool()
async def get_task_status(task_id: str) -> str:
    """
    Check the status and get artifacts of a parsed task.
    
    Args:
        task_id: The ID of the task to check (returned by parse_paper).
    """
    if not API_KEY:
        return "Error: MDTERO_API_KEY environment variable is not set."
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/tasks/{task_id}",
                headers={"ApiKey": API_KEY},
            )
            if response.status_code == 200:
                data = response.json()
                return f"Task Status: {data.get('status')}\nResults: {data.get('result', 'None yet')}"
            else:
                return f"Failed to get task status: {response.text}"
        except Exception as e:
            return f"Error connecting to Mdtero API: {str(e)}"

@mcp.tool()
async def translate_paper(source_markdown_path: str, target_language: str = "zh", mode: str = "full") -> str:
    """
    Translate a parsed markdown paper into a target language.

    Args:
        source_markdown_path: The file path to the source markdown paper.
        target_language: The target language code (e.g., 'zh' for Chinese).
        mode: The translation mode ('full', 'abstract_only', etc.).
    """
    if not API_KEY:
        return "Error: MDTERO_API_KEY environment variable is not set. Please generate one at https://mdtero.com/account"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/tasks/translate",
                headers={"ApiKey": API_KEY},
                json={
                    "source_markdown_path": source_markdown_path,
                    "target_language": target_language,
                    "mode": mode
                },
                timeout=60.0
            )
            if response.status_code == 200:
                data = response.json()
                task_id = data.get("task_id")
                return f"Successfully initiated translation task. Task ID: {task_id}\nCheck your Mdtero dashboard to download the translated artifact."
            else:
                return f"Failed to translate paper: {response.text}"
        except Exception as e:
            return f"Error connecting to Mdtero API: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
