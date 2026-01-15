# Agent Task Template

Use this template to create tasks for the AI Agent.

> [!IMPORTANT]
> All tasks must follow **Test-Driven Development (TDD)**. Write tests *before* implementation.

## Directives
The following fields are parsed by the agent to control execution. They can be placed anywhere in the issue body, but typically go at the top.

- **Priority**: `[High|Medium|Low]` (Informational)
- **Estimated Time**: `[e.g., 1 day]` (Informational)
- **Base**: `[Source Branch Name]` (Optional. Defaults to `main`. The branch to checkout *from*.)
- **Branch**: `[Target Branch Name]` (Optional. Defaults to `feat/issue-{id}-{title}`)
- **Dependencies**: `#[Issue ID]` (Optional. Agent will wait until this issue is Closed.)

## Test Requirements (TDD - Write First!)
[Specify the tests that must be written *before* implementation. Include:
- Unit tests for core logic
- Edge cases to handle
- Expected behavior descriptions]

## Description
[Provide a clear, step-by-step description of the task. Be specific about what needs to be changed and where.]

## Acceptance Criteria
- [ ] All tests written and initially failing (Red)
- [ ] Implementation makes tests pass (Green)
- [ ] Code refactored for clarity (Refactor)
- [ ] [Additional conditions...]
