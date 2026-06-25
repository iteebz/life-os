~/life/.git is the parent repo. subrepos are flat alongside it, each with their own .git/:
- eam/, taxing/, tynice/, tynice-com/, life-os/
- all gitignored from the parent. each has its own remote on github.
- `cd <name>` before any git operation on a subrepo. git from ~/life hits the parent.
- commit from the repo that owns the file. never `git add eam/...` from the parent.

tynice/ is the shared doc layer between tyson and janice. both stewards rebase on top.
- always `git pull --rebase` before adding docs — janice's steward may have pushed.
- keep docs factual and tidy. this is shared context, not a journal.
