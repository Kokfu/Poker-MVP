"""Poker Coach (Phase 5F): advice for manually entered hands plus opponent profiles.

The user types in their own cards, the board, and the public actions.  Every
spot is replayed through the authoritative ``HandEngine`` so illegal entries
are rejected, then ``SolverBot`` (or its exploitative variant with the stored
profile of the named opponent) recommends a play.  Completed hands can be
logged per opponent in a local SQLite file; profiles are rebuilt from those
public action histories with the same ``OpponentModel`` used by the bots.

Input is manual by design: there is no screen reading, site integration, or
automation.  Using real-time assistance while playing on a poker site breaks
most sites' rules; the Coach is meant for study, review, and practice.
"""
