# Loaded automatically by gunicorn from the working directory, whatever start
# command Render uses.
#
# One worker on purpose: the live-refresh status lives in that process's memory.
# Threads so a slow SEO audit or PageSpeed run (15-40 s) doesn't freeze the
# tracker for everyone else, and a timeout long enough for PageSpeed to finish.
workers = 1
threads = 8
timeout = 120
