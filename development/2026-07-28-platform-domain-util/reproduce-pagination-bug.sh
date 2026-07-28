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

# describe <expected first id, or EMPTY> -> the expectation in words
describe_expectation() {
    if [ "$1" = "EMPTY" ]; then
        echo "an empty array -- there are no sites after the last one"
    else
        echo "$LIMIT elements, the first being $1"
    fi
}

# run_case <heading> <verdict-word> <explanation> <cursor> <expected first id, or EMPTY>
#
# One self-contained block per case: what is being asked, the exact command, the expected
# answer, the answer actually received, and the tally over $REPEATS requests.  The first
# request is made with -D - so that the status, the Date header and the body all come from
# the SAME response; the remaining REPEATS-1 requests only feed the tally.
run_case() {
    local heading="$1" verdict_word="$2" explanation="$3" cursor="$4" expected="$5"
    local url raw status date_hdr body first length verdict
    local correct=0 repeated=0 other=0 i page

    url="$API/organizations/$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT"
    [ -n "$cursor" ] && url="$url&start=$cursor"

    echo "==============================================================================="
    echo "$heading"
    echo "==============================================================================="
    printf '%s\n' "$explanation"
    echo
    echo "  Command:"
    echo "    curl -s -H \"Authorization: Bearer \$SESSION\" \\"
    echo "      \"$url\""
    echo

    raw=$(curl -s -D - -H "Authorization: Bearer $session" "$url") || die "request failed for $url"
    status=$(printf '%s\n' "$raw" | head -1 | tr -d '\r' | sed 's/[[:space:]]*$//')
    date_hdr=$(printf '%s\n' "$raw" | tr -d '\r' | grep -i '^date:' | head -1)
    body=$(printf '%s\n' "$raw" | awk 'in_body {print} /^\r?$/ {in_body = 1}')
    case "$status" in
        *200*) ;;
        *) die "$url returned '$status' (expected 200); stopping rather than reporting a verdict" ;;
    esac
    length=$(printf '%s' "$body" | jq 'length')
    first=$(printf '%s' "$body" | jq -r '.[0].id // empty')
    verdict=$(classify "$body" "$expected")

    echo "  Expected:  $(describe_expectation "$expected")"
    if [ "$length" -eq 0 ]; then
        echo "  Actual:    $status, an empty array"
    else
        echo "  Actual:    $status, $length elements, the first being $first"
    fi
    if [ "$verdict" = "PAGE-1-AGAIN" ]; then
        echo "             ^^ that is the FIRST site in the collection: the cursor was"
        echo "                ignored and the listing restarted from the beginning."
    elif [ "$verdict" = "CORRECT" ]; then
        echo "             ^^ as expected."
    fi
    echo "  Response $date_hdr"
    echo

    case "$verdict" in
        CORRECT)      correct=1 ;;
        PAGE-1-AGAIN) repeated=1 ;;
        *)            other=1 ;;
    esac
    for ((i = 1; i < REPEATS; i++)); do
        page=$(get_page "$cursor") || die "a repeat request failed; see the message above"
        case $(classify "$page" "$expected") in
            CORRECT)      correct=$((correct + 1)) ;;
            PAGE-1-AGAIN) repeated=$((repeated + 1)) ;;
            *)            other=$((other + 1)) ;;
        esac
    done
    printf '  Over %d identical requests:  correct=%d  returned-page-1-again=%d  other=%d   <-- %s\n' \
        "$REPEATS" "$correct" "$repeated" "$other" "$verdict_word"
    echo
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
# Two controls (A, D) and two defect cases (B, C).  The controls matter: they are what
# rules out "your session was degrading" or "the collection reordered underneath you" --
# those would break A and D too, and they pass in the same run.

run_case \
    "CASE A  (CONTROL)  cursor = the last id of page 1, i.e. the id of site $LIMIT" \
    "as documented" \
    "  This is the one cursor value that works, and it is why the defect is easy to miss:
  a caller that walks the collection by passing the last id of each page it receives
  never notices anything wrong.  Asking to start after site $LIMIT correctly returns a page
  beginning at site $((LIMIT + 1))." \
    "$(id_at $LIMIT)" "$(id_at $((LIMIT + 1)))"

run_case \
    "CASE B  (DEFECT)   cursor = the first id of page 2, i.e. the id of site $((LIMIT + 1))" \
    "DEFECT" \
    "  The cursor is a real site UUID in this organization, returned by this very endpoint
  in the page before.  It differs from CASE A only in being one position further along,
  so asking to start after site $((LIMIT + 1)) must return a page beginning at site $((LIMIT + 2)).
  It is not a page boundary of any pagination the caller has requested, which appears to
  be what matters." \
    "$(id_at $((LIMIT + 1)))" "$(id_at $((LIMIT + 2)))"

run_case \
    "CASE C  (DEFECT)   cursor = the id of the FIRST site in the collection, site 1" \
    "DEFECT" \
    "  This one closes the \"only use cursors we issued you\" explanation.  The id below is
  the first element of the first page the API returned, in the very response it was
  returned in -- there is no more API-issued id available.  Asking to start after site 1
  must return a page beginning at site 2." \
    "$(id_at 1)" "$(id_at 2)"

run_case \
    "CASE D  (CONTROL)  cursor = the id of the LAST site in the collection, site $total" \
    "as documented" \
    "  The end of the collection behaves correctly: asking to start after the final site
  returns an empty array, which is how a caller is supposed to learn it is done.  That
  makes the defect above more surprising, not less -- the cursor IS understood here." \
    "$(id_at "$total")" "EMPTY"

echo "Finished (UTC): $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo
echo "Reading the verdicts: 'returned-page-1-again' counts responses that were the first"
echo "page of the collection instead of the page after the cursor -- HTTP 200, no error of"
echo "any kind.  Any nonzero count is the defect.  ('other' would mean a response that was"
echo "neither the expected page nor the first page; it should never occur, since every"
echo "non-200 stops the script instead of producing a verdict.)"
