"""Workboard bounded context (ADR-276): a personal ticket board.

Six columns on screen — seven while « à confirmer » holds a ticket, the only
one drawn conditionally — with tickets carrying a priority, dates, one level of
sub-tickets and comments. A ticket is assigned to the person, to LIA, or to a connected peer —
and a ticket assigned to LIA is EXECUTED by LIA out of turn, through the same
pipeline a routine uses (lot 2).

One row per ticket, shared by its owner and its assignee: the board of user U
is « owner = U or assignee = U ». There are no per-board copies, so the two
sides can never disagree about a ticket's state.
"""
