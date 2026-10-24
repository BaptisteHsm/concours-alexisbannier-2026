"""Recompte les votes du Concours Mariés 2026 (post Instagram Dew8r4MjIzV)
et met à jour tally.json, lu par index.html.

Règles : premier numéro de 1 à 20 trouvé dans le commentaire (les @mentions
sont ignorées), un seul vote par compte (le premier), réponses comprises,
commentaires postés après la fin des votes ignorés.

Variable d'environnement requise : IG_SESSIONID (cookie « sessionid »).
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
import http.cookiejar

MEDIA_ID = "4012974166055357653"
PARIS = ZoneInfo("Europe/Paris")
END = dt.datetime(2026, 10, 25, 19, 0, tzinfo=PARIS)  # dimanche 25 octobre, 19h (heure d'hiver)
TALLY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tally.json")

MENTION = re.compile(r"@[\w.]+")
NUMBER = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")


def vote_of(text):
    for m in NUMBER.finditer(MENTION.sub(" ", text or "")):
        n = int(m.group(1))
        if 1 <= n <= 20:
            return n
    return None


def count(comments):
    votes, seen = {}, set()
    for c in sorted(comments, key=lambda c: c["ts"]):
        if c["ts"] > END.timestamp():
            continue
        n = vote_of(c["text"])
        if n is None or c["user"] in seen:
            continue
        seen.add(c["user"])
        votes[str(n)] = votes.get(str(n), 0) + 1
    return dict(sorted(votes.items(), key=lambda kv: int(kv[0])))


class Instagram:
    def __init__(self, sessionid):
        jar = http.cookiejar.CookieJar()
        user_id = urllib.parse.unquote(sessionid).split(":")[0]
        csrf = os.environ.get("IG_CSRFTOKEN", "").strip() or "missing"
        for name, value in (("sessionid", sessionid), ("ds_user_id", user_id), ("csrftoken", csrf)):
            jar.set_cookie(http.cookiejar.Cookie(
                0, name, value, None, False, ".instagram.com", True, True,
                "/", True, True, None, False, None, None, {}))
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
            "X-IG-App-ID": "936619743392459",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "Referer": "https://www.instagram.com/p/Dew8r4MjIzV/",
            "X-CSRFToken": csrf,
            "X-ASBD-ID": "129477",
            "X-IG-WWW-Claim": "0",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

    def get(self, path, params=None):
        url = "https://www.instagram.com" + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self.headers)
        with self.opener.open(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return json.loads(body)
            except ValueError:
                snippet = " ".join(body[:300].split())
                raise RuntimeError(f"réponse non JSON (HTTP {r.status}, URL finale {r.geturl()}) : {snippet}")

    def comments(self):
        out, min_id = {}, None
        for _ in range(150):
            params = {"can_support_threading": "true", "permalink_enabled": "false"}
            if min_id:
                params["min_id"] = min_id
            j = self.get(f"/api/v1/media/{MEDIA_ID}/comments/", params)
            batch = j.get("comments") or []
            for c in batch:
                out[c["pk"]] = c
            min_id = j.get("next_min_id")
            if not min_id or not batch:
                break
            time.sleep(1)
        result = []
        for c in out.values():
            result.append({"user": c["user"]["username"], "text": c.get("text", ""), "ts": c["created_at"]})
            if c.get("child_comment_count"):
                j = self.get(f"/api/v1/media/{MEDIA_ID}/comments/{c['pk']}/child_comments/")
                for k in j.get("child_comments") or []:
                    result.append({"user": k["user"]["username"], "text": k.get("text", ""), "ts": k["created_at"]})
                time.sleep(1)
        return result


def main():
    now = dt.datetime.now(PARIS)
    if now > END + dt.timedelta(hours=1):
        print("Votes terminés, rien à faire.")
        return 0
    sessionid = os.environ.get("IG_SESSIONID", "").strip()
    if not sessionid:
        print("::error::Secret IG_SESSIONID manquant.")
        return 1
    try:
        comments = Instagram(sessionid).comments()
    except Exception as e:  # réseau, session expirée, blocage Instagram
        print(f"::warning::Lecture Instagram impossible : {e}")
        return 0
    votes = count(comments)
    if not votes:
        print("::warning::Aucun vote lu (session expirée ?). tally.json inchangé.")
        return 0

    with open(TALLY, encoding="utf-8") as f:
        old = json.load(f)
    stamp = now.replace(microsecond=0).isoformat()
    print(f"{len(comments)} commentaires, {sum(votes.values())} votes : {votes}")
    if votes == old.get("votes"):
        print("Aucun nouveau vote.")
        return 0
    new = dict(old, checked=stamp, updated=stamp, votes=votes,
               prevUpdated=old.get("updated"), prev=old.get("votes", {}))
    with open(TALLY, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
