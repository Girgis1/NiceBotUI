# Grok Rules

## Core Principles
- **Never directly edit code**: All code changes must be documented as instructions in Grok.md
- **Instruction-based changes**: Provide clear, actionable steps for implementing changes
- **Date/time tracking**: Every change instruction must include timestamp
- **Clean documentation**: Keep Grok.md organized and up-to-date
- **TODO management**: Use TODO sections at the top when relevant

## Process
1. Identify issues and solutions
2. Document change instructions in Grok.md with timestamps
3. Do not make direct code edits
4. Provide clear file paths, line numbers, and exact code changes needed
5. Test instructions for clarity and completeness

## File Structure
- `GrokRules.md`: This rules document
- `Grok.md`: Change instructions and documentation

## Guidelines
- Use markdown formatting for clarity
- Include context for each change
- Provide before/after code examples when helpful
- Mark completed changes appropriately
- Keep historical record of all change instructions
- **Provide detailed reasoning**: Explain the "why" behind each change to help other agents understand the logic and implications
- **Thorough impact analysis**: Always review how edits could cause potential issues elsewhere in the codebase before suggesting changes
