---
name: revue-hebdomadaire
description: >
  Trigger ONLY when the user explicitly asks for a weekly review: a review,
  recap or check-in of their WHOLE week ("my weekly review", "review my week",
  "weekly recap", "end-of-week review", "weekly check-in"). Reads the tasks
  completed and still open, the tracked
  commitments, the next seven days of the calendar and the pending reminders,
  then answers in four parts: done, still open, the week ahead, to decide. A
  question about one category or item ("my meetings this week", "my tasks",
  "what is due tomorrow") is NEVER this skill: leave skill_name null and use
  the matching functional domain.
category: organisation
priority: 60
plan_template:
  deterministic: true
  steps:
    - step_id: get_completed_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters:
        only_completed: true
      depends_on: []
      description: Completed tasks (the review keeps those finished in the past seven days)
    - step_id: get_open_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters:
        show_completed: false
      depends_on: []
      description: Tasks still open, overdue first
    - step_id: get_commitments
      agent_name: setting_agent
      tool_name: get_lia_open_loops_tool
      parameters: {}
      depends_on: []
      description: Open commitments tracked from conversations, owed and awaited
    - step_id: get_week_ahead
      agent_name: event_agent
      tool_name: get_events_tool
      parameters:
        days_ahead: 7
      depends_on: []
      description: The calendar of the next seven days
    - step_id: get_reminders
      agent_name: reminder_agent
      tool_name: list_reminders_tool
      parameters: {}
      depends_on: []
      description: Pending reminders
---

# Weekly review

## Instructions

Answer in the user's language. Today's date and time zone are in your context:
"the past week" is the seven days before today, "the week ahead" the seven days
from today.

1. **Done** — the tasks completed in the past seven days (read their completion
   or last update date; leave older ones out). A few words each, no commentary.
2. **Still open** — the open tasks, overdue first (say how late), then those due
   in the week ahead; the tracked commitments, each with its direction (what the
   user owes, what they wait for) and for how long it has been open; the
   reminders due in the week ahead.
3. **The week ahead** — the next seven days of the calendar, day by day, naming
   overlaps and the busiest days.
4. **To decide** — at most three points that need a decision: an overdue task to
   reschedule or drop, a commitment open for a long time, an overlap to resolve.
   One line each, something the user can act on.

Rules:

- A part whose data was not read (its step did not run: a capability switched
  off, no account connected) is left out, never shown as empty. "Nothing open"
  is said only of data that was read and holds nothing.
- A read that failed is named in one line; the rest of the review still stands.
- Short lines, no introduction, nothing after the "To decide" part.
- Never invent an item, a date, a status or a person.

## Available resources

- `references/output-format.md` — the layout of the review
