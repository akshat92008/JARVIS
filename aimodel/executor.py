"""
Workspace Executor & Tool Operations Engine.
Manages file writing, directory inspection, diff application, and command execution.
"""

import os
import subprocess
from pathlib import Path


class WorkspaceExecutor:
    def __init__(self, workspace_dir=None):
        self.workspace_dir = Path(workspace_dir or os.getcwd()).resolve()

    def write_file(self, relative_path, content):
        target_path = self.workspace_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(target_path)

    def read_file(self, relative_path):
        target_path = self.workspace_dir / relative_path
        if not target_path.exists():
            return None
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_workspace(self):
        items = []
        for root, _, files in os.walk(self.workspace_dir):
            for file in files:
                rel = os.path.relpath(os.path.join(root, file), self.workspace_dir)
                if not rel.startswith(".") and "__pycache__" not in rel:
                    items.append(rel)
        return items

    def run_command(self, command_str, timeout=30):
        try:
            res = subprocess.run(
                command_str,
                shell=True,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "success": res.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s: {command_str}",
                "success": False
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
