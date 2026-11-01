#!/bin/sh
# Pull the repo, regenerate the feed, and push it if it changed.
#
#   REPO        git URL to pull and push (default: this project's GitHub repo)
#   BRANCH      branch to update (default: main)
#   DEPLOY_KEY  path to the SSH deploy key with write access (default: /run/secrets/deploy_key)
#   NO_PUSH=1   commit locally but don't push (for testing)
set -eu

REPO=${REPO:-git@github.com:steve-homer/getPoolCal.git}
BRANCH=${BRANCH:-main}
DEPLOY_KEY=${DEPLOY_KEY:-/run/secrets/deploy_key}
WORK=/work/repo

if [ -f "$DEPLOY_KEY" ]; then
    # ssh refuses keys readable by others; a bind-mounted key can't be chmod'ed in place.
    install -m 600 "$DEPLOY_KEY" /tmp/deploy_key
    export GIT_SSH_COMMAND="ssh -i /tmp/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
fi

if [ -d "$WORK/.git" ]; then
    git -C "$WORK" fetch -q origin "$BRANCH"
    git -C "$WORK" reset -q --hard "origin/$BRANCH"
else
    git clone -q --branch "$BRANCH" "$REPO" "$WORK"
fi
cd "$WORK"

uv run --locked --no-dev getpoolcal ics

git add data docs
if git diff --cached --quiet; then
    echo "No changes to publish"
    exit 0
fi
git -c user.name="getpoolcal" -c user.email="13299892+steve-homer@users.noreply.github.com" \
    commit -q -m "Update fixture feed"
if [ "${NO_PUSH:-}" = 1 ]; then
    echo "NO_PUSH=1: committed locally, not pushing"
    exit 0
fi
git push -q origin "HEAD:$BRANCH"
echo "Published updated feed"
