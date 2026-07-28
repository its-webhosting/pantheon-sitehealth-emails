#!/bin/bash
#
# Reproduce: the Pantheon API's organization site-list pagination cursor (`start`) is
# silently ignored for most site ids -- the API answers HTTP 200 with the FIRST page
# again, instead of the page after the cursor and instead of any error.
#
# Standalone: needs bash, curl, jq and the usual POSIX text utilities (awk, grep,
# head, sed, sort, tr, wc).  Nothing else is read, sourced or imported.
#
# Credentials:
#   $PANTHEON_MACHINE_TOKEN   used if set; otherwise the single JSON file in
#                             ~/.terminus/cache/tokens/ is read (Terminus' own cache).
#                             The token is passed to curl on stdin, never on argv,
#                             so it is not visible in `ps` on a shared host.
# Organization:
#   $PANTHEON_ORG_ID          defaults to 23c7208e-5f2a-4388-9fc4-5c3a038ef8b9
# Tuning:
#   $REPEATS                  probes per case (default 5), so each verdict is a tally
#                             rather than a single sample.
#
# Requires an organization with at least 102 sites: the probes below need a site id
# that is provably not a page boundary, which needs at least two ids beyond the first
# page.  The script checks this and stops rather than reporting a misleading verdict.
#
# Read-only: every request is a GET except the POST that exchanges the machine token
# for a session token.  Every request is checked for HTTP 200 and the script stops on
# anything else, so a failure can never be mistaken for a defect verdict.
#
set -u

API="https://api.pantheon.io/v0"
PANTHEON_ORG_ID="${PANTHEON_ORG_ID:-23c7208e-5f2a-4388-9fc4-5c3a038ef8b9}"
REPEATS="${REPEATS:-5}"
LIMIT=100          # the maximum this endpoint documents
MIN_SITES=$((LIMIT + 2))

die() { echo "ERROR: $*" >&2; exit 1; }

for tool in curl jq awk grep sed sort tr wc; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is required but not on PATH"
done
case "$REPEATS" in
    ''|*[!0-9]*) die "REPEATS must be a positive integer, got '$REPEATS'" ;;
esac
[ "$REPEATS" -ge 1 ] || die "REPEATS must be at least 1, got '$REPEATS'"

# ---------------------------------------------------------------- credentials --
if [ -n "${PANTHEON_MACHINE_TOKEN:-}" ]; then
    machine_token="$PANTHEON_MACHINE_TOKEN"
    echo "Using \$PANTHEON_MACHINE_TOKEN"
else
    cache="$HOME/.terminus/cache/tokens"
    [ -d "$cache" ] || die "\$PANTHEON_MACHINE_TOKEN is unset and $cache does not exist"
    token_file=""
    count=0
    for candidate in "$cache"/*; do
        [ -f "$candidate" ] || continue
        token_file="$candidate"
        count=$((count + 1))
    done
    [ "$count" -eq 1 ] || die "expected exactly one token file in $cache, found $count -- set \$PANTHEON_MACHINE_TOKEN to choose one"
    machine_token=$(jq -r '.token // empty' < "$token_file")
    [ -n "$machine_token" ] || die "$token_file has no .token"
    echo "Using the machine token from ~/.terminus/cache/tokens/"
fi

# The token goes in on stdin (--data @-), not on the command line, so it never appears
# in the process table.
session=$(jq -n --arg t "$machine_token" '{machine_token: $t, client: "pagination-bug-report"}' \
    | curl -s -X POST -H "Content-Type: application/json" --data @- "$API/authorize/machine-token" \
    | jq -r '.session // empty')
[ -n "$session" ] || die "could not exchange the machine token for a session token"

echo "Started (UTC):  $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo "Organization:   $PANTHEON_ORG_ID"
echo "Endpoint:       GET $API/organizations/\$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT&start=<site id>"
echo "curl:           $(curl --version | head -1)"
echo "Client string:  pagination-bug-report  (sent in the machine-token exchange; responses"
echo "                carry no request-id header, so this is the only correlation handle)"
echo "Repeats/case:   $REPEATS"
echo

# ------------------------------------------------------------------- helpers --
# get_page [cursor] -> the JSON array on stdout; returns nonzero on any non-200.
# NOTE: this must RETURN rather than exit -- it is always called inside $( ), where an
# exit would only kill the subshell.  Every call site therefore ends in `|| die`.
get_page() {
    local url response status body
    url="$API/organizations/$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT"
    [ -n "${1:-}" ] && url="$url&start=$1"
    response=$(curl -s -w '\n%{http_code}' -H "Authorization: Bearer $session" "$url") || {
        echo "curl failed for $url" >&2
        return 1
    }
    status="${response##*$'\n'}"
    body="${response%$'\n'*}"
    if [ "$status" != "200" ]; then
        echo "GET $url returned HTTP $status (expected 200)" >&2
        return 1
    fi
    printf '%s\n' "$body"
}

# classify <json page> <expected first id, or EMPTY> -> CORRECT | PAGE-1-AGAIN | OTHER
classify() {
    local length first
    length=$(echo "$1" | jq 'length')
    first=$(echo "$1" | jq -r '.[0].id // empty')
    if [ "$2" = "EMPTY" ]; then
        [ "$length" -eq 0 ] && { echo CORRECT; return; }
    elif [ "$first" = "$2" ]; then
        echo CORRECT; return
    fi
    if [ "$first" = "$page1_first" ]; then echo PAGE-1-AGAIN; else echo OTHER; fi
}

# probe <label> <cursor> <expected first id, or EMPTY>
probe() {
    local label="$1" cursor="$2" expected="$3"
    local correct=0 repeated=0 other=0 i page
    for ((i = 0; i < REPEATS; i++)); do
        page=$(get_page "$cursor") || die "the probe request failed; see the message above"
        case $(classify "$page" "$expected") in
            CORRECT)      correct=$((correct + 1)) ;;
            PAGE-1-AGAIN) repeated=$((repeated + 1)) ;;
            *)            other=$((other + 1)) ;;
        esac
    done
    printf '  %-46s correct=%d  RETURNED-PAGE-1-AGAIN=%d  other=%d\n' \
        "$label" "$correct" "$repeated" "$other"
}

# ------------------------------------------------- collect the reference list --
echo "Collecting the site list, cursor = last id of each full page (the pattern that works) ..."
page=$(get_page) || die "could not fetch the first page"
page1_first=$(echo "$page" | jq -r '.[0].id')
page1_length=$(echo "$page" | jq 'length')
[ "$page1_length" -eq "$LIMIT" ] || die "this organization has only $page1_length sites; reproducing needs at least $MIN_SITES"

all_ids=$(echo "$page" | jq -r '.[].id')
cursor=$(echo "$page" | jq -r '.[-1].id')
pages=1
while :; do
    page=$(get_page "$cursor") || die "could not fetch the page after cursor $cursor"
    length=$(echo "$page" | jq 'length')
    [ "$length" -eq 0 ] && break
    [ "$(echo "$page" | jq -r '.[0].id')" = "$page1_first" ] && \
        die "the cursor was ignored while collecting the reference list; re-run"
    all_ids="$all_ids"$'\n'$(echo "$page" | jq -r '.[].id')
    pages=$((pages + 1))
    [ "$length" -lt "$LIMIT" ] && break
    cursor=$(echo "$page" | jq -r '.[-1].id')
done

total=$(echo "$all_ids" | wc -l | tr -d ' ')
unique=$(echo "$all_ids" | sort -u | wc -l | tr -d ' ')
[ "$total" = "$unique" ] || die "the reference walk itself returned duplicates ($total collected, $unique unique); re-run"
# Assert the ordering rather than asserting it in prose: every "expected first id" below is
# a POSITION in this list, so if the collection were not totally ordered and stable, those
# expectations would be meaningless and the verdicts below would be noise.
echo "$all_ids" | LC_ALL=C sort -c 2>/dev/null || \
    die "the collected site ids are not in ascending order; the positional expectations below would be unreliable"
[ "$total" -ge "$MIN_SITES" ] || die "this organization has $total sites; reproducing needs at least $MIN_SITES (see the header)"
echo "  $total sites over $pages pages, verified ascending by id and free of duplicates"
echo

id_at() { echo "$all_ids" | sed -n "$1p"; }      # 1-based position in that order

# --------------------------------------------------------------- the evidence --
echo "CASE A (control) -- cursor = last id of page 1 (position $LIMIT)."
echo "                    Correct answer: the page starting at site $((LIMIT + 1))."
probe "start=<id at position $LIMIT>" "$(id_at $LIMIT)" "$(id_at $((LIMIT + 1)))"
echo
echo "CASE B (defect) -- cursor = first id of page 2 (position $((LIMIT + 1)))."
echo "                   Correct answer: the page starting at site $((LIMIT + 2))."
probe "start=<id at position $((LIMIT + 1))>" "$(id_at $((LIMIT + 1)))" "$(id_at $((LIMIT + 2)))"
echo
echo "CASE C (defect) -- cursor = the FIRST site id (position 1)."
echo "                   Correct answer: the page starting at site 2."
probe "start=<id at position 1>" "$(id_at 1)" "$(id_at 2)"
echo
echo "CASE D (control) -- cursor = the LAST site id (position $total)."
echo "                    Correct answer: an empty array."
probe "start=<id at position $total>" "$(id_at "$total")" "EMPTY"
echo

# ------------------------------------------- ONE failing request, headers + body --
# Headers and body come from the SAME response, so the status shown is provably the
# status of the body shown.
b_cursor=$(id_at $((LIMIT + 1)))
b_url="$API/organizations/$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT&start=$b_cursor"
b_raw=$(curl -s -D - -H "Authorization: Bearer $session" "$b_url") || die "the demonstration request failed"
b_status=$(printf '%s\n' "$b_raw" | head -1 | tr -d '\r')
b_date=$(printf '%s\n' "$b_raw" | tr -d '\r' | grep -i '^date:' | head -1)
b_body=$(printf '%s\n' "$b_raw" | awk 'body {print} /^\r?$/ {body = 1}')

echo "The failing request from CASE B, in full:"
echo
echo "  curl -s -D - -H \"Authorization: Bearer \$SESSION\" \\"
echo "    \"$b_url\""
echo
echo "  response status:   $b_status"
echo "  response $b_date"
echo "  expected first id: $(id_at $((LIMIT + 2)))   (the site after the cursor)"
echo "  actual   first id: $(printf '%s' "$b_body" | jq -r '.[0].id')   (the first site in the collection)"
echo "  elements returned: $(printf '%s' "$b_body" | jq 'length')"
echo
echo "Finished (UTC): $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo
echo "Any nonzero RETURNED-PAGE-1-AGAIN count above is the defect: a cursored request was"
echo "answered with the first page of the collection, HTTP 200, no error of any kind."
echo "('other' would mean a response that was neither the expected page nor the first page;"
echo "it should never occur, since every non-200 stops the script instead.)"
