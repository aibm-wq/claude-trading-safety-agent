"""
Wrapper para lanzar metatrader-mcp-server con credenciales del .env del workspace.
Referenciado desde .mcp.json — mantiene credenciales fuera del config versionado.
"""
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

login = os.getenv("LOGIN")
password = os.getenv("PASSWORD")
server = os.getenv("SERVER")

if not all([login, password, server]):
    sys.exit("Error: LOGIN, PASSWORD o SERVER no están en el .env del workspace.")

exe = os.getenv("METATRADER_MCP_EXE", "metatrader-mcp-server")

result = subprocess.run(
    [exe, "--login", login, "--password", password, "--server", server, "--transport", "stdio"],
    stdin=sys.stdin,
    stdout=sys.stdout,
    stderr=sys.stderr,
)
sys.exit(result.returncode)
