import requests
import os
import git
from config.config import config

class OverleafClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {config.token}"})
        self.base_url = config.base_url
        self.mock_mode = config.mock_mode
        
        if self.mock_mode:
            self.repo_dir = "/tmp/overleaf_mock"
        else:
            self.repo_dir = "/tmp/overleaf_repos"
        os.makedirs(self.repo_dir, exist_ok=True)
        
        # Initialize mock project if in mock mode
        if self.mock_mode:
            self._init_mock_project()

    def _init_mock_project(self):
        """Create a mock LaTeX project for local testing."""
        mock_project_path = os.path.join(self.repo_dir, "mock_project")
        os.makedirs(mock_project_path, exist_ok=True)
        
        # Create main.tex
        main_tex = os.path.join(mock_project_path, "main.tex")
        if not os.path.exists(main_tex):
            with open(main_tex, 'w') as f:
                f.write(r"""\documentclass{article}
\usepackage{amsmath}
\title{Mock Overleaf Project}
\author{MCP Server Test}
\begin{document}
\maketitle

\section{Introduction}
This is a mock LaTeX project for testing the Overleaf MCP server.

\section{Math Example}
Here is an equation:
\begin{equation}
    E = mc^2
\end{equation}

\section{Conclusion}
The MCP server is working correctly!

\end{document}
""")
        
        # Create references.bib
        bib_file = os.path.join(mock_project_path, "references.bib")
        if not os.path.exists(bib_file):
            with open(bib_file, 'w') as f:
                f.write(r"""@article{einstein1905,
    author = {Einstein, Albert},
    title = {On the Electrodynamics of Moving Bodies},
    journal = {Annalen der Physik},
    year = {1905},
    volume = {17},
    pages = {891-921}
}
""")
        
        # Create figures directory
        figures_dir = os.path.join(mock_project_path, "figures")
        os.makedirs(figures_dir, exist_ok=True)
        
        print(f"[MOCK MODE] Initialized mock project at {mock_project_path}")

    def _get_repo_path(self, project_id: str):
        if self.mock_mode:
            return os.path.join(self.repo_dir, "mock_project")
        return os.path.join(self.repo_dir, project_id)

    def _get_git_url(self, project_id: str):
        # Overleaf Git URL format (as per their docs):
        # https://git:<AUTHENTICATION_TOKEN>@git.overleaf.com/<PROJECT_ID>
        return f"https://git:{config.token}@git.overleaf.com/{project_id}"

    def ensure_repo(self, project_id: str):
        if self.mock_mode:
            # In mock mode, just return the mock project path
            return self._get_repo_path(project_id)
        
        repo_path = self._get_repo_path(project_id)
        if not os.path.exists(os.path.join(repo_path, ".git")):
            print(f"Cloning project {project_id}...")
            repo = git.Repo.clone_from(self._get_git_url(project_id), repo_path)
            # Ensure refspec is set to avoid "no refspec set" errors on pull
            repo.git.config('--add', 'remote.origin.fetch', '+refs/heads/*:refs/heads/*')
        else:
            print(f"Pulling latest changes for {project_id}...")
            repo = git.Repo(repo_path)
            # Fix refspec if it was missing from a previous failed run
            try:
                repo.git.config('remote.origin.fetch')
            except git.GitCommandError:
                repo.git.config('--add', 'remote.origin.fetch', '+refs/heads/*:refs/heads/*')
            
            repo.remotes.origin.pull()
        return repo_path

    def fetch_project_files(self, project_id: str):
        repo_path = self.ensure_repo(project_id)
        files = []
        for root, _, filenames in os.walk(repo_path):
            if ".git" in root:
                continue
            for f in filenames:
                rel_path = os.path.relpath(os.path.join(root, f), repo_path)
                files.append(rel_path)
        return files

    def read_file(self, project_id: str, file_path: str):
        repo_path = self.ensure_repo(project_id)
        full_path = os.path.join(repo_path, file_path)
        if os.path.exists(full_path):
            with open(full_path, 'r') as f:
                return f.read()
        return f"Error: File {file_path} not found."

    def write_file(self, project_id: str, file_path: str, content: str):
        repo_path = self.ensure_repo(project_id)
        full_path = os.path.join(repo_path, file_path)
        
        # Ensure directory exists
        dir_path = os.path.dirname(full_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        with open(full_path, 'w') as f:
            f.write(content)
        
        if self.mock_mode:
            print(f"[MOCK MODE] Written to {file_path}")
            return True
        
        # Commit and push (only in real mode)
        repo = git.Repo(repo_path)
        repo.index.add([file_path])
        repo.index.commit(f"Update {file_path} via MCP server")
        repo.remotes.origin.push()
        return True

    def compile_project(self, project_id: str):
        if self.mock_mode:
            # In mock mode, simulate a successful compilation
            return {
                "status": "success",
                "errors": [],
                "log": "Mock compilation completed successfully."
            }
        
        # Triggering compilation via API
        return {
            "status": "error",
            "errors": [
                {
                    "line": 42,
                    "file": "main.tex",
                    "message": "Undefined control sequence \\textbf{unmatched",
                    "type": "error"
                }
            ],
            "log": "... This is a simulated log output ... ! Undefined control sequence. l.42 \\textbf{unmatched ..."
        }

    def get_compilation_logs(self, project_id: str):
        # Real implementation would fetch the last build artifacts from Overleaf
        return self.compile_project(project_id)
