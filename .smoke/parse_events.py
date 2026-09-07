import json

raw = open("ask_events.txt", encoding="utf-8").read()
out = []
sid = ""
for b in raw.split("\n\n"):
    if not b.startswith("event: "):
        continue
    data_line = next((l for l in b.split("\n") if l.startswith("data: ")), None)
    if data_line is None:
        continue
    d = json.loads(data_line.split("data: ", 1)[1])
    if "session_id" in d:
        sid = d["session_id"]
        out.append("SID=" + sid)
    if "references" in d:
        out.append("n_refs=%d" % len(d["references"]))
        out.append("ref0=" + json.dumps(d["references"][0], ensure_ascii=False)[:220])
    if "suggestions" in d:
        out.append("n_sugg=%d" % len(d["suggestions"]))
        out.append("sugg=" + json.dumps(d["suggestions"], ensure_ascii=False)[:280])
open("sid.txt", "w").write(sid)
print("\n".join(out))
