#!/usr/bin/env bash
# Ask the curated Genie questions via the Conversation API and capture the raw
# question -> generated SQL -> result-rows exchange as text evidence.
set -uo pipefail
P="${PROFILE:-icu-sandbox}"
SPACE="${SPACE_ID:?set SPACE_ID}"
OUT="${OUT:-evidence/raw/genie-qa.txt}"

questions=(
  "How many current ICU patients are ready for step-down?"
  "What is the average ICU length of stay by readiness band?"
  "How many current patients are on vasopressors and on a ventilator at the same time?"
  "What is the average heart rate and GCS for patients over 65?"
  "What fraction of ICU stays had a bounce-back within 72 hours?"
)

{
  echo "# Genie Conversation API — live question/answer capture"
  echo "# Captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)  |  space_id: $SPACE  |  profile: $P"
  echo "# Method: genie start-conversation -> poll get-message until COMPLETED -> get-message-attachment-query-result"
  echo
} > "$OUT"

qn=0
for q in "${questions[@]}"; do
  qn=$((qn+1))
  echo "===== Q$qn: $q =====" | tee -a "$OUT"
  resp=$(databricks genie start-conversation "$SPACE" "$q" --profile "$P" 2>&1)
  conv=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('conversation_id',''))" 2>/dev/null)
  msg=$(echo "$resp" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('message_id') or d.get('message',{}).get('id',''))" 2>/dev/null)
  if [ -z "$conv" ] || [ -z "$msg" ]; then
    echo "  ERROR starting conversation: $resp" | tee -a "$OUT"; continue
  fi
  echo "conversation_id: $conv" >> "$OUT"; echo "message_id: $msg" >> "$OUT"
  # poll
  status=""
  for i in $(seq 1 40); do
    m=$(databricks genie get-message "$SPACE" "$conv" "$msg" --profile "$P" 2>&1)
    status=$(echo "$m" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('status',''))" 2>/dev/null)
    [ "$status" = "COMPLETED" ] && break
    [ "$status" = "FAILED" ] && break
    [ "$status" = "CANCELLED" ] && break
    sleep 6
  done
  echo "status: $status" | tee -a "$OUT"
  # extract SQL + attachment id
  att=$(echo "$m" | python3 -c "import sys,json;d=json.load(sys.stdin);a=(d.get('attachments') or [{}])[0];print(a.get('attachment_id',''))" 2>/dev/null)
  sql=$(echo "$m" | python3 -c "import sys,json;d=json.load(sys.stdin);a=(d.get('attachments') or [{}])[0];print((a.get('query') or {}).get('query',''))" 2>/dev/null)
  txt=$(echo "$m" | python3 -c "import sys,json;d=json.load(sys.stdin);a=(d.get('attachments') or [{}])[0];print((a.get('text') or {}).get('content',''))" 2>/dev/null)
  echo "--- generated SQL ---" >> "$OUT"; echo "$sql" >> "$OUT"
  if [ -n "$att" ]; then
    echo "--- result rows ---" >> "$OUT"
    databricks genie get-message-attachment-query-result "$SPACE" "$conv" "$msg" "$att" --profile "$P" 2>&1 \
      | python3 -c "import sys,json
try:
  d=json.load(sys.stdin); sr=d.get('statement_response',d)
  res=sr.get('result',{}); rows=res.get('data_array') or res.get('data_typed_array') or res.get('data')
  sch=(sr.get('manifest',{}).get('schema',{}).get('columns')) or []
  cols=[c.get('name') for c in sch]
  print('columns:',cols)
  print('rows:',rows)
except Exception as e:
  print(sys.stdin.read())" >> "$OUT" 2>&1
  fi
  [ -n "$txt" ] && { echo "--- text answer ---" >> "$OUT"; echo "$txt" >> "$OUT"; }
  echo >> "$OUT"
done
echo "DONE -> $OUT"
