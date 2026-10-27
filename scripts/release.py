#!/usr/bin/env python3
"""Queue of Geant4 release validations, kept in issues of this repository.

Each validated Geant4 tag has one issue, "Geant4 <tag> validation", labelled
geant4-release. Its body is a readable table plus the state as JSON (between the
markers below): the dashboard reads it too. Commands:

  request   (geant4-release.yml) record a request: wait for the base image, or queue
            the tests (all, or the --tests given, e.g. to rerun the failed ones)
  advance   (release-queue.yml) follow every open validation: start the next tests,
            ask again for a base image whose build vanished, and once every test has
            finished post the report (with the comparison to the previous version)
            mentioning who asked for it, and close the issue

Tests start in ascending order of the median duration of their last successful runs
on the default branch (fastest first), at most max_parallel at a time.

Environment:
  GITHUB_REPOSITORY  this repository (owner/name)
  GITHUB_TOKEN       this repository's token: issues read/write
  DISPATCH_TOKEN     G4MED_DISPATCH_TOKEN: Actions read/write on the tests and geant4-alma9
  RESULTS_DIR        checkout of validation-results, for the report (advance)
  DASHBOARD_URL      Pages URL of the dashboard (default https://<owner>.github.io/dashboard)
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "validation"))
import compare as comparison  # noqa: E402
import tests_list  # noqa: E402

API = "https://api.github.com"
LABEL = "geant4-release"
BEGIN, END = "<!-- g4med-release", "-->"
TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[.-][A-Za-z0-9][A-Za-z0-9.-]*)?\Z")
FINAL = {"success", "failure", "cancelled", "timed_out", "startup_failure", "skipped", "neutral",
         "stale", "dispatch_failed"}
NOTIFY_JOB = "notify"  # last job of pipeline.yml; GitHub names it "run-pipeline / notify"
MAX_IMAGE_REQUESTS = 3
IMAGE_RETRY_AFTER = timedelta(minutes=20)  # a build normally shows up within seconds


class Conflict(Exception):
    """The issue changed between reading and writing it."""


def now():
    return datetime.now(timezone.utc)


def iso(t):
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


# ------------------------------------------------------------------------- GitHub

def gh(method, path, token_env="GITHUB_TOKEN", body=None, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    token = os.environ.get(token_env, "")
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28",
                                          "Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        if err.code == 404 and method == "GET":
            return None
        raise RuntimeError(f"{method} {path}: HTTP {err.code} {err.read()[:300]!r}") from None
    return json.loads(raw) if raw else None


def owner():
    return os.environ["GITHUB_REPOSITORY"].split("/")[0]


def this_repo():
    return os.environ["GITHUB_REPOSITORY"]


def base_repo():
    return f"{owner()}/geant4-alma9"


def image_published(tag):
    """Whether ghcr.io/<owner>/geant4-alma9:<tag> exists (only "not found" means no)."""
    image = f"{owner().lower()}/geant4-alma9"
    with urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:{image}:pull", timeout=30) as resp:
        token = json.load(resp)["token"]
    req = urllib.request.Request(f"https://ghcr.io/v2/{image}/manifests/{tag}", method="HEAD", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return False
        raise


def base_build_active():
    runs = gh("GET", f"/repos/{base_repo()}/actions/workflows/build.yml/runs", "DISPATCH_TOKEN",
              params={"per_page": 10}) or {}
    return any(r["status"] != "completed" and r["event"] != "pull_request" for r in runs.get("workflow_runs", []))


def request_image_build(tag):
    gh("POST", f"/repos/{base_repo()}/actions/workflows/build.yml/dispatches", "DISPATCH_TOKEN",
       body={"ref": "main", "inputs": {"geant4_tag": tag}})


def default_branch(repo, cache={}):
    if repo not in cache:
        cache[repo] = (gh("GET", f"/repos/{repo}", "DISPATCH_TOKEN") or {}).get("default_branch", "main")
    return cache[repo]


def median_duration(repo):
    """Median duration (s) of the last successful non-PR runs of ci.yml on the default branch."""
    runs = gh("GET", f"/repos/{repo}/actions/workflows/ci.yml/runs", "DISPATCH_TOKEN",
              params={"status": "success", "branch": default_branch(repo), "per_page": 30}) or {}
    durations = [(parse_time(r["updated_at"]) - parse_time(r["run_started_at"])).total_seconds()
                 for r in runs.get("workflow_runs", []) if r["event"] != "pull_request" and r.get("run_started_at")]
    return int(statistics.median(durations[:15])) if durations else None


def dispatch_test(repo, tag):
    """Start ci.yml with this Geant4 tag; the run id when GitHub returns it."""
    resp = gh("POST", f"/repos/{repo}/actions/workflows/ci.yml/dispatches", "DISPATCH_TOKEN",
              body={"ref": default_branch(repo), "inputs": {"geant4_tag": tag}, "return_run_details": True})
    return (resp or {}).get("workflow_run_id"), (resp or {}).get("html_url")


def find_run(repo, since, claimed):
    """Fallback without a run id: the oldest dispatch run of ci.yml created after `since`."""
    runs = gh("GET", f"/repos/{repo}/actions/workflows/ci.yml/runs", "DISPATCH_TOKEN",
              params={"event": "workflow_dispatch", "per_page": 20}) or {}
    for run in sorted(runs.get("workflow_runs", []), key=lambda r: r["created_at"]):
        if run["id"] not in claimed and parse_time(run["created_at"]) >= since - timedelta(seconds=30):
            return run
    return None


# -------------------------------------------------------------------------- state

def title(tag):
    return f"Geant4 {tag} validation"


def parse_state(body):
    m = re.search(re.escape(BEGIN) + r"\s*(\{.*?\})\s*" + re.escape(END), body or "", re.S)
    return json.loads(m.group(1)) if m else None


def new_state(tag):
    return {"tag": tag, "phase": None, "max_parallel": 3, "requested_by": None, "requested": None,
            "image_requests": [], "tests": []}


def select(tests_arg, listed):
    """Repositories of tests.json selected by a comma/space separated list of names (empty: all)."""
    names = [n for n in re.split(r"[,\s]+", tests_arg or "") if n]
    if not names:
        return listed
    by_name = {r.split("/")[1].lower(): r for r in listed} | {r.lower(): r for r in listed}
    unknown = [n for n in names if n.lower() not in by_name]
    if unknown:
        raise SystemExit("Not in tests.json: " + ", ".join(unknown))
    return list(dict.fromkeys(by_name[n.lower()] for n in names))


def start_tests(state, repos, explicit, median=median_duration):
    """Queue tests. Without an explicit list, a validation already running is left alone
    (only tests added to tests.json meanwhile join it); a finished one starts again."""
    phase = state.get("phase")
    if phase == "waiting-image" and not explicit and state.get("requested"):
        repos = state["requested"]
    by_repo = {t["repo"]: t for t in state["tests"]}
    for repo in repos:
        t = by_repo.get(repo)
        if t is None:
            state["tests"].append({"repo": repo, "state": "todo", "attempts": 0})
        elif phase == "running" and (not explicit or t["state"] not in FINAL):
            continue  # already queued, running, or (no explicit list) finished in this round
        else:
            t.update(state="todo", run_id=None, url=None, duration_s=None, dispatched_at=None)
    for t in state["tests"]:
        if t["state"] == "todo" and t.get("median_s") is None:
            t["median_s"] = median(t["repo"])
    state["phase"] = "running"
    state.pop("finished_at", None)


def queue_order(tests):
    """Tests still to start, fastest (by median) first; unknown durations last."""
    todo = [t for t in tests if t["state"] == "todo"]
    return sorted(todo, key=lambda t: (t.get("median_s") is None, t.get("median_s") or 0, t["repo"].lower()))


def fmt_dur(s):
    if s is None:
        return "—"
    s = int(s)
    return f"{s // 3600}h {s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m {s % 60:02d}s"


ICON = {"success": "✅", "failure": "❌", "cancelled": "⚪", "timed_out": "⏱️", "startup_failure": "❌",
        "dispatch_failed": "❌", "todo": "⏳", "stale": "⚪"}


def dashboard_url(tag):
    base = os.environ.get("DASHBOARD_URL") or f"https://{owner().lower()}.github.io/dashboard"
    return f"{base}/geant4.html?v={urllib.parse.quote(tag)}"


def render(state):
    tests = state["tests"]
    counts = {"done": sum(t["state"] in FINAL for t in tests), "todo": sum(t["state"] == "todo" for t in tests)}
    counts["running"] = len(tests) - counts["done"] - counts["todo"]
    phase = state["phase"]
    head = {"waiting-image": f"⏳ **Waiting for the base image** `ghcr.io/{owner().lower()}/geant4-alma9:{state['tag']}`: "
                             f"its build was requested {len(state['image_requests'])} time(s); the tests start once it is published.",
            "running": f"🔄 **Running**: {counts['running']} running, {counts['done']} finished, {counts['todo']} queued "
                       f"(at most {state['max_parallel']} at a time, fastest first).",
            "done": "🏁 **Finished**: see the report in the comments.",
            "failed": "❌ **Failed**: see the comments."}.get(phase, phase)
    order = {t["repo"]: i for i, t in enumerate(queue_order(tests), 1)}
    rows = []
    for t in tests:
        shown = "queued #%d" % order[t["repo"]] if t["state"] == "todo" else t["state"]
        run = "[run](%s)" % t["url"] if t.get("url") else "—"
        rows.append("| %s %s | [%s](https://github.com/%s) | %s | %s | %s |" % (
            ICON.get(t["state"], "🔄"), shown, t["repo"].split("/")[1], t["repo"],
            fmt_dur(t.get("median_s")), fmt_dur(t.get("duration_s")), run))
    return "\n".join([
        f"Validation of Geant4 **{state['tag']}** with the tests of `tests.json`"
        f"{(', requested by `%s`' % state['requested_by']) if state.get('requested_by') else ''}. "
        f"Updated by `geant4-release.yml` and `release-queue.yml`: do not edit.",
        "", head, "", f"[Dashboard]({dashboard_url(state['tag'])})", "",
        "| State | Test | Median | Duration | Run |", "| --- | --- | --- | --- | --- |", *rows, "",
        BEGIN, json.dumps(state, indent=1), END])


def find_issue(tag):
    issues = gh("GET", f"/repos/{this_repo()}/issues", params={"labels": LABEL, "state": "all", "per_page": 100}) or []
    return next((i for i in issues if i["title"] == title(tag) and "pull_request" not in i), None)


def ensure_label():
    try:
        gh("POST", f"/repos/{this_repo()}/labels", body={"name": LABEL, "color": "6f42c1",
                                                          "description": "Validation of a Geant4 version (release.py)"})
    except RuntimeError as err:
        if "HTTP 422" not in str(err):  # already exists
            raise


def save(issue, state, close=False):
    """Create or update the issue; Conflict if someone else changed it meanwhile."""
    body = render(state)
    if issue is None:
        ensure_label()
        return gh("POST", f"/repos/{this_repo()}/issues", body={"title": title(state["tag"]), "body": body, "labels": [LABEL]})
    current = gh("GET", f"/repos/{this_repo()}/issues/{issue['number']}")
    if current["updated_at"] != issue["updated_at"]:
        raise Conflict(issue["number"])
    patch = {"body": body, "state": "closed" if close else "open"}
    if close:
        patch["state_reason"] = "completed"
    return gh("PATCH", f"/repos/{this_repo()}/issues/{issue['number']}", body=patch)


def comment(issue, text):
    gh("POST", f"/repos/{this_repo()}/issues/{issue['number']}/comments", body={"body": text})


# ------------------------------------------------------------------------ request

def request(args):
    if not TAG.match(args.tag):
        raise SystemExit("Invalid Geant4 tag: " + args.tag)
    listed = [t["repo"] for t in tests_list.load()]
    repos = select(args.tests, listed)
    explicit = bool((args.tests or "").strip())
    for _ in range(5):
        issue = find_issue(args.tag)
        state = (parse_state(issue["body"]) if issue else None) or new_state(args.tag)
        # geant4-alma9 starts the request again once the image is published: keep who
        # asked for it and with which parallelism.
        if not (state.get("phase") == "waiting-image" and args.image == "published" and not explicit):
            state["max_parallel"] = args.max_parallel
            if args.actor:
                state["requested_by"] = args.actor
        if args.image == "missing":
            if state.get("phase") != "waiting-image":
                state["image_requests"] = []
            state["phase"] = "waiting-image"
            state["requested"] = repos if explicit else None
            state["image_requests"].append(iso(now()))
        else:
            start_tests(state, repos, explicit)
        try:
            issue = save(issue, state)
            break
        except Conflict:
            continue
    else:
        raise SystemExit("The issue kept changing: try again")
    print(f"{issue['html_url']}: {state['phase']}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as out:
            out.write(f"Validation of {args.tag}: [{title(args.tag)}]({issue['html_url']}) ({state['phase']})\n")


# ------------------------------------------------------------------------ advance

def refresh(t):
    """Update one dispatched test from its run."""
    if not t.get("run_id"):
        run = find_run(t["repo"], parse_time(t["dispatched_at"]), set())
        if not run:
            if now() - parse_time(t["dispatched_at"]) > timedelta(hours=1):
                t["state"] = "stale"  # dispatched, but no run ever appeared
            return
        t["run_id"], t["url"] = run["id"], run["html_url"]
    else:
        run = gh("GET", f"/repos/{t['repo']}/actions/runs/{t['run_id']}", "DISPATCH_TOKEN")
        if run is None:
            t["state"] = "stale"
            return
    t["url"] = run["html_url"]
    status, conclusion, ended = run["status"], run["conclusion"], run["updated_at"]
    if status == "in_progress":
        # The pipeline's last job (notify) starts this queue: the run is still in
        # progress then, but its work is done.
        jobs = (gh("GET", f"/repos/{t['repo']}/actions/runs/{run['id']}/jobs", "DISPATCH_TOKEN",
                   params={"per_page": 100}) or {}).get("jobs", [])
        work = [j for j in jobs if not j["name"].endswith(NOTIFY_JOB)]
        if work and all(j["status"] == "completed" for j in work):
            status, ended = "completed", max(j["completed_at"] for j in work)
            bad = [j["conclusion"] for j in work if j["conclusion"] not in ("success", "skipped", "neutral")]
            conclusion = bad[0] if bad else "success"
    t["state"] = conclusion if status == "completed" else status
    if status == "completed" and run.get("run_started_at"):
        t["duration_s"] = int((parse_time(ended) - parse_time(run["run_started_at"])).total_seconds())


def report(state):
    """Final comment: result, duration and comparison with the previous version of each test."""
    results = Path(os.environ.get("RESULTS_DIR", "validation-results"))
    version = state["tag"].removeprefix("v")
    rows, changed_total = [], 0
    for t in state["tests"]:
        name = t["repo"].split("/")[1]
        versions_dir = results / name / "versions"
        cmp = "—"
        if (versions_dir / version / "results.json").exists():
            older = sorted((d.name for d in versions_dir.iterdir()
                            if (d / "results.json").exists()
                            and comparison.version_key(d.name) < comparison.version_key(version)),
                           key=comparison.version_key)
            if older:
                ref = older[-1]
                res = comparison.compare(comparison.load(versions_dir / ref), comparison.load(versions_dir / version))
                s = res["summary"]
                changed_total += s["changed"]
                total = sum(s.values())
                extra = ", ".join(f"{s[k]} {k}" for k in ("incomparable", "new", "removed") if s[k])
                cmp = f"{'⚠️ ' if s['changed'] else ''}{s['changed']} of {total} changed vs {ref}" + (f" ({extra})" if extra else "")
            else:
                cmp = "first version with results"
        elif t["state"] == "success":
            cmp = "results not found"
        run = "[run](%s)" % t["url"] if t.get("url") else "—"
        rows.append("| %s %s | %s | %s | %s | %s |" % (ICON.get(t["state"], ""), t["state"], name,
                                                       fmt_dur(t.get("duration_s")), cmp, run))
    ok = sum(t["state"] == "success" for t in state["tests"])
    who = state.get("requested_by")
    mention = f"@{who} " if who and not who.endswith("[bot]") and who != "github-actions" else ""
    return "\n".join([
        f"{mention}Validation of Geant4 **{state['tag']}** finished: **{ok} of {len(state['tests'])} tests passed**, "
        f"{changed_total} plot(s) changed with respect to the previous version.",
        "", "| Result | Test | Duration | Plots | Run |", "| --- | --- | --- | --- | --- |", *rows, "",
        f"Changed: chi2 test of the two versions with p < {comparison.ALPHA}, or a difference above "
        f"{comparison.REL_TOL:.0%} where there are no uncertainties. Details per plot on the "
        f"[dashboard]({dashboard_url(state['tag'])})."])


def advance_one(issue):
    state = parse_state(issue["body"])
    if not state:
        print(f"#{issue['number']}: no state, skipped")
        return
    tag, close, notes = state["tag"], False, []
    if state["phase"] == "waiting-image":
        if image_published(tag):
            start_tests(state, [t["repo"] for t in tests_list.load()], explicit=False)
        elif not base_build_active() and now() - parse_time(state["image_requests"][-1]) > IMAGE_RETRY_AFTER:
            if len(state["image_requests"]) >= MAX_IMAGE_REQUESTS:
                state["phase"], close = "failed", True
                notes.append(f"{('@' + state['requested_by'] + ' ') if state.get('requested_by') else ''}"
                             f"The base image of {tag} could not be built after {MAX_IMAGE_REQUESTS} attempts: see "
                             f"[its builds](https://github.com/{base_repo()}/actions/workflows/build.yml). No test was run.")
            else:
                request_image_build(tag)
                state["image_requests"].append(iso(now()))
    if state["phase"] == "running":
        for t in state["tests"]:
            if t["state"] not in FINAL and t["state"] != "todo":
                refresh(t)
        active = sum(t["state"] not in FINAL and t["state"] != "todo" for t in state["tests"])
        for t in queue_order(state["tests"])[:max(0, state["max_parallel"] - active)]:
            try:
                t["run_id"], t["url"] = dispatch_test(t["repo"], tag)
                t["state"], t["dispatched_at"] = "requested", iso(now())
                t["attempts"] = t.get("attempts", 0) + 1
            except RuntimeError as err:
                t["state"] = "dispatch_failed"
                print(f"{t['repo']}: {err}", file=sys.stderr)
        if all(t["state"] in FINAL for t in state["tests"]):
            state["phase"], state["finished_at"], close = "done", iso(now()), True
            notes.append(report(state))
    try:
        save(issue, state, close=close)
    except Conflict:
        print(f"#{issue['number']} changed meanwhile: next run")
        return
    for note in notes:
        comment(issue, note)
    print(f"#{issue['number']} {tag}: {state['phase']}")


def advance(args):
    issues = gh("GET", f"/repos/{this_repo()}/issues", params={"labels": LABEL, "state": "open", "per_page": 100}) or []
    failed = False
    for issue in issues:
        if "pull_request" in issue:
            continue
        try:
            advance_one(issue)
        except Exception as err:  # one broken validation must not stop the others
            failed = True
            print(f"#{issue['number']}: {err}", file=sys.stderr)
    sys.exit(1 if failed else 0)


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = cli.add_subparsers(dest="command", required=True)
    r = sub.add_parser("request", help="record a validation request")
    r.add_argument("--tag", required=True)
    r.add_argument("--image", choices=["published", "missing"], required=True)
    r.add_argument("--tests", default="", help="names of the tests to (re)run, comma separated (default: all)")
    r.add_argument("--max-parallel", type=int, default=3)
    r.add_argument("--actor", default="")
    r.set_defaults(function=request)
    a = sub.add_parser("advance", help="follow every open validation")
    a.set_defaults(function=advance)
    args = cli.parse_args()
    if getattr(args, "max_parallel", 1) < 1:
        raise SystemExit("--max-parallel must be at least 1")
    args.function(args)


if __name__ == "__main__":
    main()
