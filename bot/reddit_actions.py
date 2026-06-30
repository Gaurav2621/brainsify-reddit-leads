"""
Authenticated Reddit client — used for the live stream AND for posting.

Posting a comment or DM requires a logged-in user (read-only auth can't write),
so this uses username/password on a Reddit "script" app.

⚠️ If your account has 2FA on, set REDDIT_PASSWORD to "yourpassword:123456"
   (password + current 6-digit code) or disable 2FA for this account.
"""
import os

import praw

_reddit = None


def client() -> praw.Reddit:
    global _reddit
    if _reddit is None:
        _reddit = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            username=os.environ["REDDIT_USERNAME"],
            password=os.environ["REDDIT_PASSWORD"],
            user_agent=os.environ.get("REDDIT_USER_AGENT", "lead-finder/1.0"),
            check_for_async=False,
        )
    return _reddit


def post_comment(post_id: str, text: str) -> str:
    """Reply to a submission. Returns the permalink of the new comment."""
    submission = client().submission(id=post_id)
    comment = submission.reply(text)
    return f"https://www.reddit.com{comment.permalink}"


def send_dm(username: str, subject: str, text: str) -> None:
    """Send a private message to the post's author."""
    client().redditor(username).message(subject=subject, message=text)


def valid_subreddits(names: list[str]) -> list[str]:
    """Drop subreddits that are private/banned/typo'd so they can't break the stream."""
    reddit = client()
    ok = []
    for name in names:
        try:
            _ = reddit.subreddit(name).id  # forces a fetch
            ok.append(name)
        except Exception as exc:
            print(f"[reddit] skipping r/{name}: {exc}")
    return ok
