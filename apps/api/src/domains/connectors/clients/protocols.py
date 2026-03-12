"""
Protocol classes for connector clients.

Structural typing (PEP 544) — no inheritance required.
GoogleGmailClient, AppleEmailClient, and MicrosoftOutlookClient all satisfy
EmailClientProtocol implicitly because they implement the same methods.

Used for type safety with mypy strict mode.

Created: 2026-03-10
"""

from typing import Protocol


class EmailClientProtocol(Protocol):
    """Protocol for email clients (Gmail, Apple Mail)."""

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict: ...

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict: ...

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict: ...

    async def reply_email(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
    ) -> dict: ...

    async def forward_email(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
        include_attachments: bool = True,
    ) -> dict: ...

    async def trash_email(self, message_id: str) -> dict: ...

    async def list_labels(self, use_cache: bool = True) -> dict[str, str]: ...

    async def resolve_label_names_in_query(self, query: str, use_cache: bool = True) -> str: ...


class CalendarClientProtocol(Protocol):
    """Protocol for calendar clients (Google Calendar, Apple Calendar)."""

    async def list_calendars(self, max_results: int = 100, show_hidden: bool = False) -> dict: ...

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
        calendar_id: str = "primary",
        query: str | None = None,
        fields: list[str] | None = None,
    ) -> dict: ...

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict: ...

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict: ...

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict: ...

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict: ...


class ContactsClientProtocol(Protocol):
    """Protocol for contacts clients (Google Contacts, Apple Contacts, Microsoft Contacts)."""

    async def search_contacts(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict: ...

    async def list_connections(
        self,
        page_size: int = 100,
        page_token: str | None = None,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict: ...

    async def get_person(
        self,
        resource_name: str,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict: ...

    async def create_contact(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
    ) -> dict: ...

    async def update_contact(
        self,
        resource_name: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        address: str | None = None,
    ) -> dict: ...

    async def delete_contact(self, resource_name: str) -> bool: ...


class TasksClientProtocol(Protocol):
    """Protocol for tasks clients (Google Tasks, Microsoft To Do)."""

    async def list_task_lists(self, max_results: int = 20) -> dict: ...

    async def get_task_list(self, task_list_id: str) -> dict: ...

    async def create_task_list(self, title: str) -> dict: ...

    async def delete_task_list(self, task_list_id: str) -> bool: ...

    async def list_tasks(
        self,
        task_list_id: str = "@default",
        max_results: int = 20,
        show_completed: bool = False,
        show_hidden: bool = False,
        due_min: str | None = None,
        due_max: str | None = None,
    ) -> dict: ...

    async def get_task(self, task_list_id: str, task_id: str) -> dict: ...

    async def create_task(
        self,
        task_list_id: str = "@default",
        title: str = "",
        notes: str | None = None,
        due: str | None = None,
        parent: str | None = None,
    ) -> dict: ...

    async def update_task(
        self,
        task_list_id: str,
        task_id: str,
        title: str | None = None,
        notes: str | None = None,
        due: str | None = None,
        status: str | None = None,
    ) -> dict: ...

    async def complete_task(self, task_list_id: str, task_id: str) -> dict: ...

    async def delete_task(self, task_list_id: str, task_id: str) -> bool: ...
