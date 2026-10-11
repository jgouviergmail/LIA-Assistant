"""Compatibility name; every mutation shares the ordered account/pair/ticket fence."""

from src.domains.workboard.mutation_fence import lock_mutation_ticket as lock_comment_ticket

__all__ = ["lock_comment_ticket"]
