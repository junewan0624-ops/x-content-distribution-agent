#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only fetch of an X (Twitter) account's own posts and metrics.

Pure standard library. Requires OAuth 1.0a user-context credentials with
read-only scopes: tweet.read, users.read, offline.access.

Commands:
  me                                     print the authenticated user
  history --account @handle [--pages N] [--offline]
  tweet <tweet_id> [--account @handle]

Environment:
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

Cache: work/<account>.json (merged in place, never deletes tweets).
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://api.twitter.com"
CACHE_SUBDIR = "work"
METRICS_FIELDS = "created_at,public_metrics,non_public_metrics,organic_metrics"
PUBLIC_ONLY_FIELDS = "created_at,public_metrics"
ENGAGEMENT_KEYS = (
    "like_count",
    "reply_count",
    "retweet_count",
    "quote_count",
    "bookmark_count",
)


class ApiError(Exception):
    pass


def pct(value):
    return urllib.parse.quote(str(value), safe="")


def credentials():
    names = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise ApiError("Missing environment variables: " + ", ".join(missing))
    return {name: os.environ[name] for name in names}


def oauth_header(method, url, query, cred):
    oauth = {
        "oauth_consumer_key": cred["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": cred["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    params = dict(query)
    params.update(oauth)
    encoded = "&".join("%s=%s" % (pct(k), pct(params[k])) for k in sorted(params))
    base_string = "&".join([method.upper(), pct(url), pct(encoded)])
    key = pct(cred["X_API_SECRET"]) + "&" + pct(cred["X_ACCESS_TOKEN_SECRET"])
    signature = base64.b64encode(
        hmac.new(key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    auth = dict(oauth)
    auth["oauth_signature"] = signature
    header = ", ".join('%s="%s"' % (pct(k), pct(v)) for k, v in sorted(auth.items()))
    return "OAuth " + header


def api_get(path, query):
    cred = credentials()
    url = API_BASE + path
    full_url = url
    if query:
        full_url = url + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        full_url,
        headers={
            "Authorization": oauth_header("GET", url, query, cred),
            "User-Agent": "x-content-optimizer-agent/0.1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), False
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        if (
            error.code == 403
            and "non_public_metrics" in str(query.get("tweet.fields", ""))
        ):
            degraded_query = dict(query)
            degraded_query["tweet.fields"] = PUBLIC_ONLY_FIELDS
            data, _ = api_get(path, degraded_query)
            return data, True
        raise ApiError("HTTP %s: %s" % (error.code, body[:600]))
    except urllib.error.URLError as error:
        raise ApiError("Network error: %s" % error.reason)


def cache_file(account=None):
    directory = os.path.join(os.getcwd(), CACHE_SUBDIR)
    os.makedirs(directory, exist_ok=True)
    name = (account or "single").lstrip("@") + ".json"
    return os.path.join(directory, name)


def read_cache(path):
    if not os.path.exists(path):
        return {"fetched_at": None, "tweets": [], "degraded_metrics": False}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_cache(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def merge_tweets(cache, incoming):
    merged = {tweet["id"]: tweet for tweet in cache.get("tweets", [])}
    for tweet in incoming:
        merged[tweet["id"]] = tweet
    return sorted(merged.values(), key=lambda t: t.get("created_at", ""), reverse=True)


def show_me():
    data, _ = api_get("/2/users/me", {"user.fields": "id,name,username,protected"})
    user = data.get("data") or {}
    print("id=%s" % user.get("id"))
    print("username=@%s" % user.get("username"))
    print("name=%s" % user.get("name"))
    print("protected=%s" % user.get("protected"))


def fetch_history(account, pages, offline):
    handle = account.lstrip("@")
    path = cache_file(handle)
    cache = read_cache(path)
    if offline:
        return cache
    data, _ = api_get(
        "/2/users/by/username/" + urllib.parse.quote(handle),
        {"user.fields": "id,name,username,protected"},
    )
    user = data.get("data") or {}
    if not user:
        raise ApiError("Account not found or not accessible: @" + handle)
    query = {
        "tweet.fields": METRICS_FIELDS,
        "max_results": "100",
        "exclude": "retweets,replies",
    }
    tweets = []
    degraded = False
    next_token = None
    for _ in range(max(1, pages)):
        page_query = dict(query)
        if next_token:
            page_query["pagination_token"] = next_token
        data, page_degraded = api_get("/2/users/%s/tweets" % user["id"], page_query)
        degraded = degraded or page_degraded
        batch = data.get("data") or []
        tweets.extend(batch)
        meta = data.get("meta") or {}
        next_token = meta.get("next_token")
        if not next_token or not batch:
            break
    payload = {
        "fetched_at": now_iso(),
        "account": {
            "id": user.get("id"),
            "username": user.get("username"),
            "name": user.get("name"),
        },
        "tweets": merge_tweets(cache, tweets),
        "degraded_metrics": degraded or cache.get("degraded_metrics", False),
    }
    write_cache(path, payload)
    return payload


def fetch_tweet(tweet_id, account):
    path = cache_file(account) if account else cache_file("single")
    cache = read_cache(path) if account else None
    data, degraded = api_get(
        "/2/tweets/" + urllib.parse.quote(tweet_id),
        {"tweet.fields": METRICS_FIELDS},
    )
    tweet = data.get("data")
    if not tweet:
        raise ApiError("Tweet not found or not accessible: " + tweet_id)
    if cache is not None:
        cache["fetched_at"] = now_iso()
        cache["degraded_metrics"] = cache.get("degraded_metrics", False) or degraded
        cache["tweets"] = merge_tweets(cache, [tweet])
        write_cache(path, cache)
    return tweet, degraded


def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return (values[0], values[0], values[0])
    if len(values) == 2:
        return (values[0], values[0], values[1])
    if len(values) == 3:
        return (values[0], values[1], values[2])
    cut = statistics.quantiles(values, n=4, method="inclusive")
    return (cut[0], cut[1], cut[2])


def print_summary(payload):
    account = payload.get("account") or {}
    tweets = payload.get("tweets", [])
    print("account=@%s" % account.get("username", "?"))
    print("tweets_in_cache=%d" % len(tweets))
    print("fetched_at=%s" % payload.get("fetched_at"))
    print("degraded_metrics=%s" % payload.get("degraded_metrics", False))
    impressions = []
    rates = []
    for tweet in tweets:
        public = tweet.get("public_metrics") or {}
        non_public = tweet.get("non_public_metrics") or {}
        impression_count = non_public.get("impression_count")
        if impression_count is None:
            continue
        engagement = sum(public.get(key, 0) for key in ENGAGEMENT_KEYS)
        impressions.append(impression_count)
        rates.append(engagement / impression_count if impression_count else 0.0)
    if not impressions:
        print("baseline=unavailable (no impression data; check degraded_metrics)")
        return
    imp_q = quantiles(impressions)
    rate_q = quantiles(rates)
    print("impressions_p25_p50_p75=%s" % ",".join(str(v) for v in imp_q))
    print(
        "engagement_rate_p25_p50_p75=%s" % ",".join("%.4f" % v for v in rate_q)
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Read-only X account history and metrics fetcher"
    )
    parser.add_argument("command", choices=["me", "history", "tweet"])
    parser.add_argument("--account", help="account handle, e.g. @handle")
    parser.add_argument("--pages", type=int, default=5, help="max pages of history")
    parser.add_argument("--offline", action="store_true", help="read cache only")
    parser.add_argument("tweet_id", nargs="?", help="tweet id for the tweet command")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        if args.command == "me":
            show_me()
        elif args.command == "history":
            if not args.account:
                raise ApiError("history requires --account @handle")
            print_summary(fetch_history(args.account, args.pages, args.offline))
        elif args.command == "tweet":
            if not args.tweet_id:
                raise ApiError("tweet requires a tweet id")
            tweet, degraded = fetch_tweet(args.tweet_id, args.account)
            print("id=%s" % tweet.get("id"))
            print("created_at=%s" % tweet.get("created_at"))
            print("public_metrics=%s" % json.dumps(tweet.get("public_metrics") or {}))
            non_public = tweet.get("non_public_metrics") or {}
            if non_public:
                print("non_public_metrics=%s" % json.dumps(non_public))
            print("degraded_metrics=%s" % degraded)
    except ApiError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
