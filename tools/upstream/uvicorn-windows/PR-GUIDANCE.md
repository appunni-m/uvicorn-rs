# Focus an upstream fix on the observed blocked accept

The standalone issue is ready to report. A production fix is not yet validated.
Use `ISSUE.md`, the two small scripts, and the retained failure/stack/wakeup
evidence. The observations support these concrete next steps:

1. Trace the Windows listener from `Config.bind_socket()` through spawn socket
   reduction, `Server.startup()`'s `_share_socket()`, and
   `loop.create_server()`. Record socket identities, process IDs, sharing and
   blocking-mode transitions. Keep this diagnostic separate from the unmodified
   baseline. The failing stack shows the selector callback entered `accept()`
   and did not return until a further connection arrived.
2. Change the smallest operation that lets a shared listener enter a blocking
   accept. Check that all workers preserve a usable nonblocking listener while
   another worker initializes or exits. Windows socket state is shared across
   duplicated descriptors according to the
   [Winsock sharing contract](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-wsaduplicatesocketw).
   Python's cached `getblocking()` value alone cannot establish every other
   descriptor's state.
3. Run the same stock-only input against baseline and proposed fix with the
   same Python, dependencies, two-worker setting, readiness observations, one
   HTTP request, and one Ctrl+C. Retain every attempt and stop on a failure.
   Require both workers to finish and the supervisor to exit with code 0
   within the original deadline, without the post-timeout wakeup connection.
4. Add a focused Windows integration regression that also observes event-loop
   responsiveness while the shared listener is idle after traffic. Exercise
   worker startup overlap and a worker exiting while another remains alive.
   Add the existing worker/reload tests relevant to the actual changed path.

The earlier `socket.listen()` `WinError(10022)` startup crash has not reproduced
in this small probe. Investigate it separately, with
[closed upstream PR #2778](https://github.com/Kludex/uvicorn/pull/2778) as prior
context. It proposed serializing socket sharing, but its change has not been
validated against this shutdown stall or current Uvicorn 0.54.0 here.

The primary success condition is a responsive worker that shuts down normally.
The captured blocking syscall and successful TCP wakeup identify a smaller
problem than a generic Windows shutdown timeout. No upstream issue or PR has
been posted; the maintainer will submit them manually.
