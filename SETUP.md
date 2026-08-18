# X -> Discord, with no server

RSSHub runs inside the GitHub Actions job and is destroyed when the job ends.
Nothing is hosted. Nothing costs money.

---

## PHASE 1 - throwaway X account

1. Open a private / incognito browser window
2. Go to x.com and create a new account with a spare email
3. Complete verification
4. STAY LOGGED IN

Never use your real account. If X flags it for automation you lose it.

## PHASE 2 - get the auth_token cookie

Still in the incognito window:

1. Press F12 (Cmd+Option+I on Mac)
2. Click the "Application" tab
3. Left sidebar: Cookies -> https://x.com
4. Find the row where Name = auth_token
5. Double-click its Value, select all, copy
6. Save it somewhere. It is roughly 40 hex characters.
7. DO NOT log out of that account - logging out kills the token

## PHASE 3 - GitHub repo

1. github.com -> New repository
2. Name it anything. Set it to PUBLIC.
   Public matters: unlimited free Actions minutes. Private is capped at 2000/month.
3. Upload these four files, keeping watch.yml inside .github/workflows/

## PHASE 4 - two secrets

Repo -> Settings -> Secrets and variables -> Actions -> New repository secret

Secret 1
  Name:  TWITTER_AUTH_TOKEN
  Value: the cookie from Phase 2

Secret 2
  Name:  DISCORD_WEBHOOK
  Value: your Discord webhook URL

Secrets are encrypted. They are not visible in logs or to anyone browsing the repo.

## PHASE 5 - first run

1. Actions tab -> "I understand my workflows, go ahead and enable them"
2. Click "X to Discord" in the left list
3. Click "Run workflow" -> "Run workflow"
4. Watch it run - takes about 60 seconds

The first run records what already exists WITHOUT posting, so you are not
flooded with 20 old tweets. Every run after that posts only new items.

## PHASE 6 - check it worked

Open the run and expand "Check feeds and post to Discord".

  FIRST RUN - recording current items without posting
  checking: ICT
    20 items in feed          <- RSSHub and the cookie are working
    20 new

If it says "0 items in feed", the cookie is wrong or expired.
Expand "RSSHub logs on failure" to see the actual error.

## PHASE 7 - Discord notifications

Right-click #ict-feed -> Notification Settings -> All Messages
On mobile: long-press the channel -> Notifications -> All Messages

---

## Going faster than 5 minutes

GitHub's minimum cron interval is 5 minutes. To beat it, duplicate
watch.yml as watch2.yml, watch3.yml etc and add a delay as the first step:

    - name: Offset
      run: sleep 60      # 120 in the next file, 180 in the one after

Five files with offsets 0/60/120/180/240 gives roughly 1-minute polling.
Still free on a public repo.

Do not go below ~60 seconds. Every poll hits X with your cookie, and
hammering it is what gets a session flagged.

---

## If it breaks

X changes its internals regularly. When that happens RSSHub's community
usually ships a fix within days - you get it automatically because the
workflow always pulls the latest diygod/rsshub image.

If the cookie expires (you logged out, or X invalidated it), redo Phase 2
and update the TWITTER_AUTH_TOKEN secret. Nothing else changes.
