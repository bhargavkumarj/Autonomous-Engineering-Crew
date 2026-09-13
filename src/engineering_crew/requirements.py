"""Built-in requirements to run the crew against.

A requirement is the crew's entire input: one block of plain English describing
what the software should do. Everything else — the design, the modules, the API,
the UI, the tests — is produced by the agents.

These are deliberately of the same size and shape: a self-contained domain with
clear invariants that a test engineer can actually assert on. That is not
incidental. Requirements with vague success conditions ("make it user-friendly")
produce crews that argue with themselves; requirements with hard rules ("prevent
withdrawing below zero") produce tests that either pass or do not.
"""

from __future__ import annotations

TRADING_ACCOUNT = """
A simple account management system for a trading simulation platform.
The system should allow users to create an account, deposit funds, and withdraw funds.
The system should allow users to record that they have bought or sold shares, providing a quantity.
The system should calculate the total value of the user's portfolio, and the profit or loss from the initial deposit.
The system should be able to report the holdings of the user at any point in time.
The system should be able to report the profit or loss of the user at any point in time.
The system should be able to list the transactions that the user has made over time.
The system should prevent the user from withdrawing funds that would leave them with a negative balance, or
 from buying more shares than they can afford, or selling shares that they don't have.
 The system has access to a function get_share_price(symbol) which returns the current price of a share, and includes a test implementation that returns fixed prices for AAPL, TSLA, GOOGL.
"""

LIBRARY = """
A lending library management system.
The system should allow books to be added to the catalogue with a title, author and ISBN, and allow multiple copies of the same ISBN.
The system should allow members to join with a name and a member id.
The system should allow a member to borrow an available copy of a book, and to return it.
The system should record the date a book was borrowed and the date it is due, with a loan period of 14 days.
The system should report which books are currently on loan, which are available, and which are overdue as of a given date.
The system should calculate a fine of 20 cents per day for each overdue book.
The system should prevent a member from borrowing more than 5 books at once, from borrowing a book with no available copies,
 and from returning a book they did not borrow.
"""

TASK_SCHEDULER = """
A task scheduling and dependency system.
The system should allow tasks to be added with an id, a name, an estimated duration in hours, and a list of task ids it depends on.
The system should reject a dependency on a task that does not exist, and reject any dependency cycle.
The system should compute a valid execution order that respects all dependencies.
The system should compute the earliest start time and earliest finish time for every task, assuming unlimited parallel workers.
The system should identify the critical path: the longest chain of dependent tasks, which determines the total project duration.
The system should report which tasks can be worked on at the same time.
The system should allow a task to be marked complete, and report which tasks are unblocked as a result.
"""

CATALOGUE = {
    "trading": TRADING_ACCOUNT,
    "library": LIBRARY,
    "scheduler": TASK_SCHEDULER,
}

DEFAULT = "trading"
