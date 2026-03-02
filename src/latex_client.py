import os
import subprocess
import git
from config.config import config


class LaTeXClient:
    """
    LaTeX project client that supports:
    - Local mode: Works with any folder containing .tex files
    - Overleaf mode: Syncs with Overleaf via Git (requires premium)
    """
    
    def __init__(self):
        self.mode = config.mode
        
        if self.mode == "local":
            self.project_path = os.path.expanduser(config.project_path)
            os.makedirs(self.project_path, exist_ok=True)
            print(f"[LOCAL MODE] Using project at: {self.project_path}")
        else:
            self.repo_dir = "/tmp/overleaf_repos"
            os.makedirs(self.repo_dir, exist_ok=True)
            print(f"[OVERLEAF MODE] Will sync to: {self.repo_dir}")

    def _get_project_path(self, project_id: str = None):
        """Get the path to the project files."""
        if self.mode == "local":
            return self.project_path
        else:
            return os.path.join(self.repo_dir, project_id or config.project_id)

    def _get_git_url(self, project_id: str):
        """Get Overleaf Git URL."""
        return f"https://git:{config.token}@git.overleaf.com/{project_id}"

    def _ensure_overleaf_repo(self, project_id: str):
        """Clone or pull Overleaf repo."""
        repo_path = self._get_project_path(project_id)
        
        if not os.path.exists(os.path.join(repo_path, ".git")):
            print(f"Cloning Overleaf project {project_id}...")
            repo = git.Repo.clone_from(self._get_git_url(project_id), repo_path)
            repo.git.config('--add', 'remote.origin.fetch', '+refs/heads/*:refs/heads/*')
        else:
            print(f"Pulling latest from Overleaf...")
            repo = git.Repo(repo_path)
            try:
                repo.git.config('remote.origin.fetch')
            except git.GitCommandError:
                repo.git.config('--add', 'remote.origin.fetch', '+refs/heads/*:refs/heads/*')
            repo.remotes.origin.pull()
        
        return repo_path

    def list_files(self, project_id: str = None):
        """List all files in the project."""
        if self.mode == "overleaf":
            project_path = self._ensure_overleaf_repo(project_id)
        else:
            project_path = self._get_project_path()
        
        files = []
        for root, _, filenames in os.walk(project_path):
            # Skip hidden directories
            if any(part.startswith('.') for part in root.split(os.sep)):
                continue
            for f in filenames:
                rel_path = os.path.relpath(os.path.join(root, f), project_path)
                files.append(rel_path)
        
        return files

    def read_file(self, file_path: str, project_id: str = None):
        """Read content of a file."""
        if self.mode == "overleaf":
            project_path = self._ensure_overleaf_repo(project_id)
        else:
            project_path = self._get_project_path()
        
        full_path = os.path.join(project_path, file_path)
        
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        return f"Error: File '{file_path}' not found."

    def write_file(self, file_path: str, content: str, project_id: str = None):
        """Write content to a file."""
        if self.mode == "overleaf":
            project_path = self._ensure_overleaf_repo(project_id)
        else:
            project_path = self._get_project_path()
        
        full_path = os.path.join(project_path, file_path)
        
        # Create directories if needed
        dir_path = os.path.dirname(full_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Push to Overleaf if in overleaf mode
        if self.mode == "overleaf":
            repo = git.Repo(project_path)
            repo.index.add([file_path])
            repo.index.commit(f"Update {file_path} via LaTeX MCP")
            repo.remotes.origin.push()
            return f"Updated '{file_path}' and pushed to Overleaf"
        
        return f"Updated '{file_path}'"

    def compile_latex(self, main_file: str = "main.tex", project_id: str = None):
        """Compile LaTeX project and return status/errors."""
        if self.mode == "overleaf":
            project_path = self._ensure_overleaf_repo(project_id)
        else:
            project_path = self._get_project_path()
        
        main_path = os.path.join(project_path, main_file)
        
        if not os.path.exists(main_path):
            return {
                "status": "error",
                "message": f"Main file '{main_file}' not found",
                "errors": []
            }
        
        try:
            # Run pdflatex
            result = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", main_file],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse log for errors
            errors = self._parse_latex_log(project_path, main_file)
            
            if result.returncode == 0:
                return {
                    "status": "success",
                    "message": "Compilation successful",
                    "pdf": main_file.replace('.tex', '.pdf'),
                    "errors": errors
                }
            else:
                return {
                    "status": "error",
                    "message": "Compilation failed",
                    "errors": errors,
                    "log_snippet": result.stdout[-1000:] if result.stdout else ""
                }
                
        except FileNotFoundError:
            return {
                "status": "error",
                "message": "pdflatex not installed. Install TeX Live: sudo apt install texlive-latex-base",
                "errors": []
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Compilation timed out",
                "errors": []
            }

    def _parse_latex_log(self, project_path: str, main_file: str):
        """Parse .log file for errors."""
        log_file = os.path.join(project_path, main_file.replace('.tex', '.log'))
        errors = []
        
        if not os.path.exists(log_file):
            return errors
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines):
            if line.startswith('!'):
                error = {"message": line.strip()}
                # Try to find line number
                for j in range(i, min(i + 5, len(lines))):
                    if lines[j].startswith('l.'):
                        parts = lines[j].split(' ', 1)
                        error["line"] = int(parts[0][2:])
                        break
                errors.append(error)
        
        return errors

    def get_project_outline(self, project_id: str = None):
        """Extract document structure (sections, chapters, etc.)."""
        if self.mode == "overleaf":
            project_path = self._ensure_overleaf_repo(project_id)
        else:
            project_path = self._get_project_path()
        
        outline = []
        tex_files = [f for f in self.list_files(project_id) if f.endswith('.tex')]
        
        import re
        section_pattern = re.compile(
            r'\\(part|chapter|section|subsection|subsubsection)\*?\{([^}]+)\}'
        )
        
        for tex_file in tex_files:
            content = self.read_file(tex_file, project_id)
            if content.startswith("Error:"):
                continue
            
            for match in section_pattern.finditer(content):
                outline.append({
                    "file": tex_file,
                    "type": match.group(1),
                    "title": match.group(2),
                    "line": content[:match.start()].count('\n') + 1
                })
        
        return outline
