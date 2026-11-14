"""One boot identity for every durable activity owned by this worker process."""

from uuid import uuid4

# Imported by workers, never by the lightweight supervisor. An OS PID reused
# after a restart cannot acquire the old process's invocation or file writes.
WORKER_BOOT_ID = uuid4()
