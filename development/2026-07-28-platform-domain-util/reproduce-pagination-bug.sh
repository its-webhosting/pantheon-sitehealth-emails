#!/bin/bash
#
# Reproduce: the Pantheon API's organization site-list pagination cursor (`start`) is
# silently ignored for most site ids -- the API answers HTTP 200 with the FIRST page
# again, instead of the page after the cursor and instead of any error.
#
# Standalone: needs only bash, curl and jq.  Nothing else is read, sourced or imported.
#
# Credentials:
#   $PANTHEON_MACHINE_TOKEN   used if set; otherwise the single JSON file in
#                             ~/.terminus/cache/tokens/ is read (Terminus' own cache).
# Organization:
#   $PANTHEON_ORG_ID          defaults to 23c7208e-5f2a-4388-9fc4-5c3a038ef8b9
# Tuning:
#   $REPEATS                  probes per case (default 5), so each verdict is a tally
#                             rather than a single sample.
#
# Read-only: every request is a GET except the POST that exchanges the machine token
# for a session token.  Requires an organization with more than 100 sites.
#
set -u

API="https://api.pantheon.io/v0"
PANTHEON_ORG_ID="${PANTHEON_ORG_ID:-23c7208e-5f2a-4388-9fc4-5c3a038ef8b9}"
REPEATS="${REPEATS:-5}"
LIMIT=100          # the maximum this endpoint documents

die() { echo "ERROR: $*" >&2; exit 1; }

for tool in curl jq; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is required but not on PATH"
done

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
    echo "Using the machine token from $token_file"
fi

session=$(curl -s -X POST -H "Content-Type: application/json" \
    "$API/authorize/machine-token" \
    -d "{\"machine_token\": \"$machine_token\", \"client\": \"pagination-bug-report\"}" \
    | jq -r '.session // empty')
[ -n "$session" ] || die "could not exchange the machine token for a session token"

echo "Organization: $PANTHEON_ORG_ID"
echo "Endpoint:     GET $API/organizations/\$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT&start=<site id>"
echo "Repeats per case: $REPEATS"
echo

# ------------------------------------------------------------------- helpers --
# get_page [cursor] -> the raw JSON array
get_page() {
    local url="$API/organizations/$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT"
    [ -n "${1:-}" ] && url="$url&start=$1"
    curl -s -H "Authorization: Bearer $session" "$url"
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
    local correct=0 repeated=0 other=0 i
    for ((i = 0; i < REPEATS; i++)); do
        case $(classify "$(get_page "$cursor")" "$expected") in
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
page=$(get_page)
page1_first=$(echo "$page" | jq -r '.[0].id')
page1_length=$(echo "$page" | jq 'length')
[ "$page1_length" -eq "$LIMIT" ] || die "this organization has only $page1_length sites; reproducing needs more than $LIMIT"

all_ids=$(echo "$page" | jq -r '.[].id')
cursor=$(echo "$page" | jq -r '.[-1].id')
pages=1
while :; do
    page=$(get_page "$cursor")
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
echo "  $total sites over $pages pages, ascending by id, no duplicates"
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
echo "CASE D (context) -- cursor = the LAST site id (position $total)."
echo "                    Correct answer: an empty array."
probe "start=<id at position $total>" "$(id_at "$total")" "EMPTY"
echo

# ------------------------------------------------- one failing request in full --
echo "The failing request from CASE B, in full:"
echo
echo "  curl -s -H \"Authorization: Bearer \$SESSION\" \\"
echo "    \"$API/organizations/$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT&start=$(id_at $((LIMIT + 1)))\""
echo
echo "  expected first id: $(id_at $((LIMIT + 2)))   (the site after the cursor)"
echo "  actual   first id: $(get_page "$(id_at $((LIMIT + 1)))" | jq -r '.[0].id')   (the first site in the collection)"
echo "  HTTP status:       $(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $session" \
    "$API/organizations/$PANTHEON_ORG_ID/memberships/sites?limit=$LIMIT&start=$(id_at $((LIMIT + 1)))")"
echo
echo "Any nonzero RETURNED-PAGE-1-AGAIN count above is the defect: a cursored request was"
echo "answered with the first page of the collection, HTTP 200, no error of any kind."
