# Gitea Skills — Bug Report & Feature Request

This document details the bugs, limitations, and sharp edges encountered while attempting to push a new project to GitHub using the `gitea-skills` plugin, along with recommendations for the Gitea skills development AI.

***

## 1. Bug: Hardcoded Keychain Service Name (`friendly-davinci-github`)

### Description
In `github_auth.py` and `github_credential_helper.py`, the Keychain service name is hardcoded:
```python
SERVICE = "friendly-davinci-github"
```
This forces all Gitea skills projects on a user's machine to share a single global GitHub Personal Access Token (PAT) under that service name in the macOS Keychain. 

### Impact
If a developer works on multiple projects (e.g., `friendly-davinci` and `ai_piano_transcriptor`) that require different GitHub scopes or belong to different accounts/organizations, they cannot store repository-scoped PATs. Overwriting it for one project breaks the sync loop for other projects.

### Proposed Fix (Feature Request)
Modify the token resolution to support project-scoped tokens (e.g., checking environment variables or the local project's `.agentic_dev/tokens.env` configuration) before falling back to the Keychain:

1. **Check Environment Variable**: Check for `GITHUB_TOKEN` or `GITHUB_PAT`.
2. **Check Local Config**: Parse `.agentic_dev/tokens.env` (already git-ignored) for `GITHUB_TOKEN` or `GITHUB_PAT`.
3. **Fallback to Keychain**: If not found locally, query the macOS Keychain. For Keychain storage, use a service name derived from the repository name if possible (e.g., `gitea-skills-<repo_name>`) rather than a hardcoded string.

***

## 2. Sharp Edge: GitHub fine-grained PAT Scope Requirements for Pull Requests

### Description
When running `gitea-skills push-to-github`, the push of git contents succeeds, but the pull request creation fails with:
```
GitHub API Error: Resource not accessible by personal access token
```

### Impact
This error occurs when using GitHub's **Fine-grained Personal Access Tokens** if they only have "Contents" read/write permissions enabled. On GitHub, creating a Pull Request via the REST API (`POST /repos/{owner}/{repo}/pulls`) requires explicit **"Pull requests" (Read and write)** permissions.

### Proposed Fix (Documentation & Error Handling)
1. **Improve Error Message**: If the API returns `403 Forbidden` with "Resource not accessible by personal access token", output a clear troubleshooting message instructing the user to enable **"Pull requests: Read and write"** under repository permissions for their fine-grained token.
2. **Setup Instructions Update**: Document this specific permission requirement in the Gitea skills README and setup guides.

***

## 3. Bug: Syncing to an Empty GitHub Repository

### Description
If the target GitHub repository is newly created and completely empty (contains no commits or branches), `push_to_github.sh` tries to create a PR into `main`.

### Impact
Because the `main` branch does not exist yet on the GitHub remote, the Pull Request creation fails because the base branch (`main`) is missing.

### Proposed Fix
The sync script should check if the target branch (`main`) exists on the remote first. If the remote has no branches:
1. It should perform a direct push to initialize the base branch (e.g., `git push -u github main`).
2. Skip the Pull Request creation step for this initial sync.

***

## 4. Sharp Edge: macOS Keychain Caching & Git Precedence Conflict

### Description
On macOS, Git is typically configured globally to use the system Keychain helper (`osxkeychain`). When running git commands, Git prioritizes the cached credentials in `osxkeychain` for `github.com` over the custom credentials passed by the Gitea skills helper.

### Impact
If the user's macOS Keychain has an existing cached token/password for `github.com` (associated with the `rfarnham` account), Git will use it. If that cached token does not have write access to the newly created `ai_piano_transcriptor` repository (even if the user supplied a new, repo-scoped PAT for this project), GitHub immediately returns `403 Forbidden` (Permission Denied). 

This happens *before* Git queries Gitea skills' custom credential helper, causing the push command to fail.

### Proposed Fix
1. **Clear Local Credential Helpers**: Gitea skills should configure the local repository to ignore the global `osxkeychain` helper for the `github` remote, or run:
   ```bash
   git config --local credential.helper ""
   ```
   This clears inherited global helpers for the repository, forcing Git to use the Gitea-skills-provided credential helper.
2. **Troubleshooting Guide**: Add a troubleshooting section in the setup docs explaining how to clear cached GitHub credentials from the macOS Keychain (using Access Keychain utility or command line `git credential-osxkeychain erase`).

***

## 5. Bug: Gitea Agent Collaborator Permissions Required for PRs

### Description
When running `gitea-skills pr create`, the API request fails with `403 Forbidden: user must be a collaborator` if the repository was created by the `admin` account but Gitea skills is using `developer-agent` credentials.

### Impact
Any newly created repository on Gitea owned by `admin` is inaccessible to the agentic development loop. The agents cannot create branches, open pull requests, or push commits to the Gitea remote unless they are explicitly added as collaborators.

### Proposed Fix
The setup script (`gitea-skills install` or a new repository init script) should automatically use the `ADMIN_TOKEN` to add the `developer-agent` and `reviewer-agent` accounts as collaborators on the newly created repository with `write` permissions:
```python
gitea_api.add_collaborator(admin_token, repo_owner, repo_name, "developer-agent", "write")
gitea_api.add_collaborator(admin_token, repo_owner, repo_name, "reviewer-agent", "write")
```
