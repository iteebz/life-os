~/life/.git is the parent repo. code lives under ~/life/repos/, each repo with its own .git/:
- repos/life-os/, repos/taxing/, repos/tynice/, repos/tynice-com/, repos/finance/, repos/observatory/
- all gitignored from the parent. each has its own remote on github.
- `cd repos/<name>` before any git operation on a subrepo. git from ~/life hits the parent.
- commit from the repo that owns the file. never `git add repos/...` from the parent.
- if a repo lands outside `repos/`, move it there.

repos/tynice/ is the shared doc layer between tyson and janice. both stewards rebase on top.
- always `git pull --rebase` before adding docs — janice's steward may have pushed.
- keep docs factual and tidy. this is shared context, not a journal.
