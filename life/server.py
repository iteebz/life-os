"""Life dashboard web server — accessible over Tailscale."""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .habit import check_habit, get_habits
from .lib.clock import today
from .lib.store import get_db
from .task import check_task, get_tasks

app = FastAPI()


def _habit_checked_today(habit) -> bool:
    t = today()
    return any(c.date() == t for c in habit.checks)


def _build_data():
    tasks = [t for t in get_tasks() if t.completed_at is None]
    habits = get_habits()
    today_str = today().isoformat()

    task_list = [
        {
            "id": t.id,
            "content": t.content,
            "focus": t.focus,
            "tags": t.tags,
        }
        for t in sorted(tasks, key=lambda t: (not t.focus, t.created))
    ]

    habit_list = [
        {
            "id": h.id,
            "content": h.content,
            "done": _habit_checked_today(h),
            "tags": h.tags,
        }
        for h in habits
    ]

    done_count = sum(1 for h in habit_list if h["done"])
    return {
        "date": today_str,
        "tasks": task_list,
        "habits": habit_list,
        "habits_done": done_count,
        "habits_total": len(habit_list),
    }


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>life</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0a0a0a;
    --surface: #141414;
    --border: #222;
    --text: #e8e8e8;
    --muted: #666;
    --accent: #a0f0a0;
    --warn: #f0c080;
    --done: #444;
    --radius: 12px;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
    font-size: 16px;
    min-height: 100dvh;
    padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
  }
  .header {
    padding: 20px 20px 12px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .header h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }
  .header .date { color: var(--muted); font-size: 14px; }
  .score {
    margin: 0 20px 20px;
    background: var(--surface);
    border-radius: var(--radius);
    padding: 14px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .score .bar-wrap { flex: 1; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  .score .bar { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
  .score .label { color: var(--muted); font-size: 13px; white-space: nowrap; }
  section { margin: 0 20px 24px; }
  section h2 { font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }
  .item {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: opacity 0.15s;
    user-select: none;
  }
  .item:active { opacity: 0.7; }
  .item.done { opacity: 0.4; }
  .item .check {
    width: 22px; height: 22px;
    border-radius: 50%;
    border: 2px solid var(--border);
    flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.15s;
  }
  .item.done .check { background: var(--accent); border-color: var(--accent); }
  .item.done .check::after { content: "✓"; font-size: 13px; color: #0a0a0a; font-weight: 700; }
  .item .text { flex: 1; line-height: 1.3; }
  .item.focus .text { font-weight: 600; }
  .item .tag { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .focus-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); flex-shrink: 0; }
  .empty { color: var(--muted); font-size: 14px; text-align: center; padding: 20px 0; }
  .refresh-hint { text-align: center; color: var(--muted); font-size: 12px; padding: 0 0 40px; }
</style>
</head>
<body>
<div id="app">
  <div class="header">
    <h1>life</h1>
    <span class="date" id="date-label"></span>
  </div>
  <div class="score">
    <span class="label" id="score-label">habits</span>
    <div class="bar-wrap"><div class="bar" id="score-bar" style="width:0%"></div></div>
  </div>
  <section>
    <h2>tasks</h2>
    <div id="tasks"></div>
  </section>
  <section>
    <h2>habits</h2>
    <div id="habits"></div>
  </section>
  <p class="refresh-hint">pull to refresh</p>
</div>
<script>
let data = null;

async function load() {
  const res = await fetch('/api/data');
  data = await res.json();
  render();
}

function render() {
  if (!data) return;
  document.getElementById('date-label').textContent = data.date;
  const pct = data.habits_total ? Math.round(data.habits_done / data.habits_total * 100) : 0;
  document.getElementById('score-bar').style.width = pct + '%';
  document.getElementById('score-label').textContent = `${data.habits_done}/${data.habits_total} habits`;

  const tasksEl = document.getElementById('tasks');
  if (!data.tasks.length) {
    tasksEl.innerHTML = '<p class="empty">all clear</p>';
  } else {
    tasksEl.innerHTML = data.tasks.map(t => `
      <div class="item${t.focus ? ' focus' : ''}" onclick="toggleTask('${t.id}', this)">
        ${t.focus ? '<div class="focus-dot"></div>' : ''}
        <div class="text">
          <div>${t.content}</div>
          ${t.tags.length ? `<div class="tag">${t.tags.map(x => '#'+x).join(' ')}</div>` : ''}
        </div>
      </div>
    `).join('');
  }

  const habitsEl = document.getElementById('habits');
  habitsEl.innerHTML = data.habits.map(h => `
    <div class="item${h.done ? ' done' : ''}" id="habit-${h.id}" onclick="toggleHabit('${h.id}', this)">
      <div class="check"></div>
      <div class="text">
        <div>${h.content}</div>
        ${h.tags.length ? `<div class="tag">${h.tags.map(x => '#'+x).join(' ')}</div>` : ''}
      </div>
    </div>
  `).join('');
}

async function toggleTask(id, el) {
  el.style.opacity = '0.4';
  await fetch('/api/task/' + id + '/done', { method: 'POST' });
  await load();
}

async function toggleHabit(id, el) {
  const habit = data.habits.find(h => h.id === id);
  if (!habit) return;
  const endpoint = habit.done ? '/api/habit/' + id + '/uncheck' : '/api/habit/' + id + '/check';
  el.style.opacity = '0.4';
  await fetch(endpoint, { method: 'POST' });
  await load();
}

load();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/api/data")
def api_data():
    return _build_data()


@app.post("/api/task/{task_id}/done")
def api_task_done(task_id: str):
    check_task(task_id)
    return {"ok": True}


@app.post("/api/habit/{habit_id}/check")
def api_habit_check(habit_id: str):
    check_habit(habit_id)
    return {"ok": True}


@app.post("/api/habit/{habit_id}/uncheck")
def api_habit_uncheck(habit_id: str):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM habit_checks WHERE habit_id = ? AND DATE(check_date) = DATE(?)",
            (habit_id, today().isoformat()),
        )
    return {"ok": True}


def serve(host: str = "0.0.0.0", port: int = 5005):
    uvicorn.run(app, host=host, port=port, log_level="warning")
