#!/usr/bin/env python3
import os
import subprocess
import sys
from watcher.config import Config

def prompt(message, default=None):
    """Simple prompt with default value."""
    if default:
        user_input = input(f"{message} [{default}]: ")
        return user_input.strip() or default
    else:
        user_input = input(f"{message}: ")
        return user_input.strip()

def run_gh_command(args):
    """Run a GitHub CLI command."""
    try:
        subprocess.run(['gh'] + args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running gh command: {e}")
        sys.exit(1)

def main():
    print("🤖 Agent Box Task Creator")
    print("-------------------------")

    # 1. Select Repository
    repos = Config.get_github_repos()
    
    if not repos:
        print("Error: No repositories configured in environment.")
        repo_input = prompt("Enter full repository name (owner/repo)")
    elif len(repos) == 1:
        repo_input = repos[0]
        print(f"Using repository: {repo_input}")
    else:
        print("\nAvailable Repositories:")
        for idx, r in enumerate(repos):
            print(f"[{idx + 1}] {r}")
        
        while True:
            choice = prompt("Select repository (number) or enter name", "1")
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(repos):
                    repo_input = repos[idx]
                    break
            elif '/' in choice:
                repo_input = choice
                break
            print("Invalid selection.")

    # 2. Basic Info
    title = prompt("Task Title")
    if not title:
        print("Title is required.")
        sys.exit(1)

    # 3. Directives
    print("\n--- Configuration (Optional) ---")
    priority = prompt("Priority (High/Medium/Low)", "Medium")
    est_time = prompt("Estimated Time", "")
    
    base_branch = prompt("Base Branch (Source)", "main")
    target_branch = prompt("Target Branch Name (Leave empty to auto-generate)", "")
    
    dependencies = prompt("Dependencies (Issue IDs, comma separated)", "")

    # 4. Description
    print("\n--- Description ---")
    print("Enter description (End with Ctrl+D or Ctrl+Z on new line, or just press Enter for simple one-line):")
    try:
        lines = sys.stdin.read()
        description = lines.strip()
    except KeyboardInterrupt:
        description = ""
    
    # 5. Build Issue Body
    body_lines = []
    
    # Header Directives
    if priority:
        body_lines.append(f"**Priority:** {priority}")
    if est_time:
        body_lines.append(f"**Estimated Time:** {est_time}")
    if base_branch and base_branch != "main":
        body_lines.append(f"**Base:** {base_branch}")
    if target_branch:
        body_lines.append(f"**Branch:** {target_branch}")
    if dependencies:
        # Format dependencies nicely
        dep_list = [f"#{d.strip()}" if not d.strip().startswith('#') else d.strip() for d in dependencies.split(',') if d.strip()]
        if dep_list:
            body_lines.append(f"**Dependencies:** {', '.join(dep_list)}")
            
    body_lines.append("") # Spacer
    body_lines.append("## Description")
    body_lines.append(description)
    
    final_body = "\n".join(body_lines)
    
    # Add TDD enforcement
    final_body += "\n\n## Test Requirements (TDD)\n"
    final_body += "_Tests must be written before implementation._\n"
    final_body += "\n## Acceptance Criteria\n"
    final_body += "- [ ] Tests written and initially failing (Red)\n"
    final_body += "- [ ] Implementation makes tests pass (Green)\n"
    final_body += "- [ ] Code refactored for clarity (Refactor)\n"
    
    # 6. Preview & Confirm
    print("\n" + "="*40)
    print(f"Title: {title}")
    print(f"Repo:  {repo_input}")
    print("-" * 20)
    print(final_body)
    print("="*40 + "\n")
    
    confirm = prompt("Create this issue? (y/n)", "y")
    if confirm.lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    # 7. Submit
    cmd = [
        'issue', 'create',
        '--repo', repo_input,
        '--title', title,
        '--body', final_body,
        '--label', Config.TRIGGER_LABEL
    ]
    
    print("Submitting...")
    run_gh_command(cmd)
    print("\n✅ Task created successfully!")

if __name__ == "__main__":
    main()
