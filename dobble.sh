#!/usr/bin/env bash

set -e

# ---------------------------
# Load .env
# ---------------------------
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
else
  echo ".env file not found"
  exit 1
fi

if [ -z "$NEO4J_URI" ] || [ -z "$NEO4J_USER" ] || [ -z "$NEO4J_PASSWORD" ]; then
  echo "Missing Neo4j credentials in .env"
  exit 1
fi

ROUNDS=${ROUNDS:-10}
COL_WIDTH=6

echo "1 or 2 players?"
read PLAYERS

score1=0
score2=0

# ---------------------------
# Play Turn
# ---------------------------
play_turn () {

  PLAYER=$1

  echo "" >&2
  echo "===== Round $r =====" >&2
  echo "" >&2
  echo "Player $PLAYER turn" >&2

  # Fetch two random cards
  OUTPUT=$(cypher-shell \
    -a "$NEO4J_URI" \
    -u "$NEO4J_USER" \
    -p "$NEO4J_PASSWORD" \
    --format plain --wrap false "
    MATCH (c:Card)
    WITH c ORDER BY rand()
    LIMIT 2
    WITH collect(c) AS cards
    UNWIND cards AS c
    MATCH (c)<-[:ON]-(s:Symbol)
    RETURN c.cardId, collect(s.emoji)
    ORDER BY c.cardId;
  " | sed '1d')

  # Parse card IDs
  cardA=$(echo "$OUTPUT" | head -n1 | awk -F',' '{print $1}' | xargs)
  cardB=$(echo "$OUTPUT" | tail -n1 | awk -F',' '{print $1}' | xargs)

  # Extract emoji lists
  rawA=$(echo "$OUTPUT" | head -n1 | sed 's/^[^[]*\[//' | sed 's/\].*//')
  rawB=$(echo "$OUTPUT" | tail -n1 | sed 's/^[^[]*\[//' | sed 's/\].*//')

  cleanA=$(echo "$rawA" | tr -d '"')
  cleanB=$(echo "$rawB" | tr -d '"')

  # Split into arrays and trim whitespace
  IFS=',' read -ra rawA_array <<< "$cleanA"
  IFS=',' read -ra rawB_array <<< "$cleanB"

  PLAYER_SYMBOLS=()
  TARGET_SYMBOLS=()

  for item in "${rawA_array[@]}"; do
    PLAYER_SYMBOLS+=("$(echo "$item" | xargs)")
  done

  for item in "${rawB_array[@]}"; do
    TARGET_SYMBOLS+=("$(echo "$item" | xargs)")
  done

  # ---------------------------
  # Display Player Card
  # ---------------------------
  echo "" >&2
  echo "Player Card ($cardA):" >&2
  echo "" >&2
  for i in "${!PLAYER_SYMBOLS[@]}"; do
    printf "  %s   |   " "${PLAYER_SYMBOLS[$i]}" >&2
  done
  echo "" >&2


  # ---------------------------
  # Display Target Card
  # ---------------------------
  echo "" >&2
  echo "Target Card ($cardB):" >&2
  echo "" >&2
  
  for i in "${!TARGET_SYMBOLS[@]}"; do
    idx=$((i+1))
    printf "%d %s   |   " "$idx" "${TARGET_SYMBOLS[$i]}" >&2
  done
  echo "" >&2

  echo "" >&2
  echo "Choose the matching emoji number:" >&2

  start=$(date +%s%N)
  read INDEX
  end=$(date +%s%N)

  elapsed=$(( (end - start)/1000000 ))

  # Validate index
  if ! [[ "$INDEX" =~ ^[1-8]$ ]]; then
    echo "Invalid choice! +3000ms penalty" >&2
    elapsed=$((elapsed + 3000))
    echo $elapsed
    return
  fi

  CHOICE=${TARGET_SYMBOLS[$((INDEX-1))]}

  # ---------------------------
  # Validate via Neo4j
  # ---------------------------
  result=$(cypher-shell \
    -a "$NEO4J_URI" \
    -u "$NEO4J_USER" \
    -p "$NEO4J_PASSWORD" \
    --format plain --wrap false "
    MATCH (c1:Card {cardId: $cardA})
    MATCH (c2:Card {cardId: $cardB})
    MATCH (s:Symbol {emoji: '$CHOICE'})
    WHERE (s)-[:ON]->(c1) AND (s)-[:ON]->(c2)
    RETURN count(s) AS correct;
  " | sed '1d' | tr -d '[:space:]')

  echo "" >&2

  if [ "$result" = "1" ]; then
    echo "Correct! ${elapsed}ms" >&2
  else
    echo "Wrong! ${elapsed}ms (penalty 3000ms)" >&2
    elapsed=$((elapsed + 3000))
  fi

  echo $elapsed
}

# ---------------------------
# Game Loop
# ---------------------------
for ((r=1; r<=ROUNDS; r++))
do
  t1=$(play_turn 1)
  score1=$((score1 + t1))

  if [ "$PLAYERS" -eq 2 ]; then
    t2=$(play_turn 2)
    score2=$((score2 + t2))
  fi
done

echo "" >&2
echo "Final Scores:" >&2
echo "Player 1: $score1 ms" >&2

if [ "$PLAYERS" -eq 2 ]; then
  echo "Player 2: $score2 ms" >&2

  if [ "$score1" -lt "$score2" ]; then
    echo "Player 1 Wins!" >&2
  else
    echo "Player 2 Wins!" >&2
  fi
else
  echo "Single player complete!" >&2
fi
