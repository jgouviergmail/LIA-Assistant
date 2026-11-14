---
name: tri-boite-reception
description: >
  Trigger ONLY when the user explicitly asks to triage or sort their inbox or
  their mail as a whole ("triage my inbox", "sort my inbox", "sort my emails",
  "what in my mail needs my attention", "what in my mail can wait"). Reads the
  unread messages of the inbox with a digest of each and sorts them into to
  answer, to read, for information, and promotions. Listing, reading,
  searching, archiving or answering particular emails ("my unread emails",
  "emails from X", "reply to Y", "archive the newsletters") is NEVER this
  skill: leave skill_name null and use the email domain.
category: quotidien
priority: 60
plan_template:
  deterministic: true
  steps:
    - step_id: get_unread_inbox
      agent_name: email_agent
      tool_name: get_emails_tool
      parameters:
        query: "in:inbox is:unread"
        detail: summary
      depends_on: []
      description: The unread messages of the inbox, each with its digest
---

# Inbox triage

## Instructions

Answer in the user's language. Put every unread message read into exactly one
group, in this order, and show only the groups that hold something:

1. **To answer** — someone expects a reply from the user: a question, a request,
   an invitation. A message whose `reply_state` is `answered` or
   `answer_drafted` never goes here.
2. **To read** — personal or work messages that need attention but no reply.
3. **For information** — notifications, receipts, confirmations, automated
   messages.
4. **Promotions and newsletters** — commercial or bulk mail: their count and
   senders on one line, not one line each.

In groups 1 to 3, each message is its sender and subject, then one line saying
why it is there, from its digest (the question asked, the deadline, the action
expected). Each group leads with its most urgent message: an explicit deadline,
an importance the digest flags.

Rules:

- Only the messages read are sorted. When unread messages remain beyond the
  page read (`next_page_token`), say how many were sorted and that more remain.
- No unread message: say so in one sentence.
- End with at most three next steps the user can ask for (reply to a named
  message, archive the promotions, read one in full). Never act: this skill
  sorts, it does not reply, archive or delete.
- Never invent a sender, a subject, a deadline or a request.

## Available resources

- `references/output-format.md` — the layout of the triage
