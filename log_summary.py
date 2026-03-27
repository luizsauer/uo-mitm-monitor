import re
from pathlib import Path
from collections import Counter, defaultdict
import json
import argparse
from datetime import datetime, timedelta

PACKET_RE = re.compile(
    r"ParsePackets: PACKET DETECTADO 0x([0-9A-Fa-f]{2})"
)
STATS_RE = re.compile(
    r"\[STATS\]\s+Sent\s+0x([0-9A-Fa-f]{2}):\s*(\d+)\s*\|\s*Received\s+0x([0-9A-Fa-f]{2}):\s*(\d+)"
)
FREEZE_RE = re.compile(r"FREEZE DETECTADO")
CRITICAL_RE = re.compile(r"CRITICAL")
ERROR_RE = re.compile(r"\bError\b", re.IGNORECASE)
WARNING_RE = re.compile(r"\bWarning\b", re.IGNORECASE)
DEBUG_RE = re.compile(r"\bDebug\b", re.IGNORECASE)
DISCONNECT_RE = re.compile(r"Normal disconnection")
DISCONNECT_TRANSITION_RE = re.compile(r"Normal disconnection during scene transition", re.IGNORECASE)
SEND_RE = re.compile(r"\[\s*-+\s*SEND\s+0x([0-9A-Fa-f]+)\s+count=(\d+)\s*-+\s*\]")
RECV_RE = re.compile(r"\[\s*-+\s*RECV\s+0x([0-9A-Fa-f]+)\s+count=(\d+)\s*-+\s*\]")
TEXTURE_ERROR_RE = re.compile(r"Texture not found for sprite: idx:\s*(\d+); itemid:\s*(\d+)", re.IGNORECASE)

TIMESTAMP_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})")

def parse_file(path, window_seconds=60):
    packet_counter = Counter()
    errors = []
    warnings = []
    debugs = []
    freeze_count = 0
    critical_count = 0
    stat_events = []
    send_event_counter = Counter()
    send_total = 0
    receive_event_counter = Counter()
    receive_total = 0
    disconnect_count = 0
    disconnect_transition_count = 0
    texture_errors = Counter()
    first_ts = None
    last_ts = None
    total_lines = 0
    base_ts = None

    # mantendo contagem por janela de tempo
    windows = defaultdict(lambda: Counter())

    def hit_window(ts, key, count=1):
        if base_ts is None:
            return
        delta = int((ts - base_ts).total_seconds())
        slot = (delta // window_seconds) * window_seconds
        windows[slot][key] += count

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_lines += 1
            m = TIMESTAMP_RE.match(line)
            ts = None
            if m:
                txt = f"{m.group(1)} {m.group(2)}"
                for fmt in ("%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
                    try:
                        ts = datetime.strptime(txt, fmt)
                        break
                    except ValueError:
                        pass

                if ts is not None:
                    if first_ts is None:
                        first_ts = ts
                        base_ts = ts
                    last_ts = ts

            if PACKET_RE.search(line):
                pid = PACKET_RE.search(line).group(1).upper()
                packet_counter[pid] += 1
                if ts:
                    hit_window(ts, f"packet_0x{pid}")

            if STATS_RE.search(line):
                m2 = STATS_RE.search(line)
                sent_id = m2.group(1).upper()
                sent_qty = int(m2.group(2))
                recv_id = m2.group(3).upper()
                recv_qty = int(m2.group(4))

                stat_events.append(
                    {
                        "sent_id": sent_id,
                        "sent": sent_qty,
                        "recv_id": recv_id,
                        "recv": recv_qty,
                    }
                )
                send_event_counter[sent_id] += sent_qty
                send_total += sent_qty
                receive_event_counter[recv_id] += recv_qty
                receive_total += recv_qty

                if ts:
                    hit_window(ts, "stats")
                    hit_window(ts, f"send_0x{sent_id}", sent_qty)
                    hit_window(ts, f"recv_0x{recv_id}", recv_qty)

            if FREEZE_RE.search(line):
                freeze_count += 1
                if ts:
                    hit_window(ts, "freeze")

            if CRITICAL_RE.search(line):
                critical_count += 1
                if ts:
                    hit_window(ts, "critical")

            if ERROR_RE.search(line):
                errors.append(line.strip())
                if ts:
                    hit_window(ts, "error")

            if WARNING_RE.search(line):
                warnings.append(line.strip())
                if ts:
                    hit_window(ts, "warning")

            if DEBUG_RE.search(line):
                debugs.append(line.strip())
                if ts:
                    hit_window(ts, "debug")

            if DISCONNECT_RE.search(line):
                if DISCONNECT_TRANSITION_RE.search(line):
                    disconnect_transition_count += 1
                else:
                    disconnect_count += 1
                if ts:
                    hit_window(ts, "disconnect")

            dsend = SEND_RE.search(line)
            if dsend:
                send_id = dsend.group(1).upper()
                send_qty = int(dsend.group(2))
                send_event_counter[send_id] += send_qty
                send_total += send_qty
                if ts:
                    hit_window(ts, f"send_0x{send_id}", send_qty)

            drecv = RECV_RE.search(line)
            if drecv:
                recv_id = drecv.group(1).upper()
                recv_qty = int(drecv.group(2))
                receive_event_counter[recv_id] += recv_qty
                receive_total += recv_qty
                if ts:
                    hit_window(ts, f"recv_0x{recv_id}", recv_qty)

            dtext = TEXTURE_ERROR_RE.search(line)
            if dtext:
                texture_key = f"idx:{dtext.group(1)} itemid:{dtext.group(2)}"
                texture_errors[texture_key] += 1
                if ts:
                    hit_window(ts, "texture_error")

    duration = None
    if first_ts and last_ts:
        duration = last_ts - first_ts

    return {
        "file": str(path),
        "total_lines": total_lines,
        "first_timestamp": first_ts.isoformat() if first_ts else None,
        "last_timestamp": last_ts.isoformat() if last_ts else None,
        "duration_seconds": int(duration.total_seconds()) if duration else 0,
        "packet_counts": packet_counter,
        "stats_entries": len(stat_events),
        "weakly_stats": stat_events[:20],
        "freeze_count": freeze_count,
        "critical_count": critical_count,
        "disconnect_count": disconnect_count,
        "disconnect_transition_count": disconnect_transition_count,
        "send_total": send_total,
        "receive_total": receive_total,
        "send_event_counter": send_event_counter,
        "receive_event_counter": receive_event_counter,
        "texture_errors": dict(texture_errors),
        "error_lines": errors[:40],
        "warning_lines": warnings[:40],
        "debug_lines": debugs[:40],
        "windows": {str(k): dict(v) for k, v in sorted(windows.items())},
    }

def format_duration(seconds):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def summarize(directory, out_json="summary.json", out_txt="summary.txt"):
    directory = Path(directory)
    results = []

    for path in sorted(directory.glob("**/*.log")):
        if "console" not in path.name and "log" not in path.suffix:
            continue

        r10 = parse_file(path, window_seconds=10)
        r30 = parse_file(path, window_seconds=30)
        r120 = parse_file(path, window_seconds=120)
        r60 = parse_file(path, window_seconds=60)

        r60["windows_10"] = r10.get("windows", {})
        r60["windows_30"] = r30.get("windows", {})
        r60["windows_120"] = r120.get("windows", {})

        def get_peak_window(windows):
            peak_slot = None
            peak_count = 0
            peak_top = []
            for slot, counts in windows.items():
                total = sum(counts.values())
                if total > peak_count:
                    peak_count = total
                    peak_slot = slot
                    peak_top = Counter(counts).most_common(8)
            return {
                "peak_slot": peak_slot,
                "peak_total": peak_count,
                "peak_top": peak_top,
            }

        r60["peak_10s"] = get_peak_window(r10.get("windows", {}))
        r60["peak_30s"] = get_peak_window(r30.get("windows", {}))
        r60["peak_120s"] = get_peak_window(r120.get("windows", {}))

        results.append(r60)

    total_duration = sum((x.get("duration_seconds",0) for x in results), 0)
    total_events = sum(sum(x.get("packet_counts", Counter()).values()) for x in results)
    aggregated = {
        "files": len(results),
        "total_lines": sum(x["total_lines"] for x in results),
        "total_freeze": sum(x["freeze_count"] for x in results),
        "total_critical": sum(x["critical_count"] for x in results),
        "total_disconnect": sum(x["disconnect_count"] for x in results),
        "total_disconnect_transition": sum(x.get("disconnect_transition_count",0) for x in results),
        "total_stats_entries": sum(x["stats_entries"] for x in results),
        "total_duration_seconds": total_duration,
        "total_duration_hms": format_duration(total_duration),
        "total_send": sum(x.get("send_total",0) for x in results),
        "total_receive": sum(x.get("receive_total",0) for x in results),
        "total_events": total_events,
        "top_send": Counter(),
        "top_receive": Counter(),
        "packets_global": Counter(),
        "peak_10s": {"peak_slot": None, "peak_total": 0, "peak_top": []},
        "peak_30s": {"peak_slot": None, "peak_total": 0, "peak_top": []},
        "peak_120s": {"peak_slot": None, "peak_total": 0, "peak_top": []},
        "errors_total": sum(len(x.get("error_lines",[])) for x in results),
        "warnings_total": sum(len(x.get("warning_lines",[])) for x in results),
        "debug_total": sum(len(x.get("debug_lines",[])) for x in results),
    }
    for r in results:
        aggregated["packets_global"].update(r["packet_counts"])
        aggregated["top_send"].update(r.get("send_event_counter", Counter()))
        aggregated["top_receive"].update(r.get("receive_event_counter", Counter()))

        for peak_key in ("peak_10s", "peak_30s", "peak_120s"):
            peak_value = r.get(peak_key, {}).get("peak_total", 0)
            if peak_value > aggregated.get(peak_key, {}).get("peak_total", 0):
                aggregated[peak_key] = r.get(peak_key)

    # packets_global is still a Counter here
    aggregated["packets_global"] = dict(aggregated["packets_global"].most_common(40))
    aggregated["top_send"] = dict(aggregated["top_send"].most_common(20))
    aggregated["top_receive"] = dict(aggregated["top_receive"].most_common(20))

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"aggregated": aggregated, "files": results}, f, indent=2, ensure_ascii=False)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("### Log summary\n")
        f.write(f"files: {aggregated['files']}\n")
        f.write(f"total lines: {aggregated['total_lines']}\n")
        f.write(f"total duration (seconds): {aggregated['total_duration_seconds']}\n")
        f.write(f"total duration (h:m:s): {format_duration(aggregated['total_duration_seconds'])}\n")
        f.write(f"freeze count: {aggregated['total_freeze']}\n")
        f.write(f"critical count: {aggregated['total_critical']}\n")
        f.write(f"disconnect (real): {aggregated['total_disconnect']}\n")
        f.write(f"disconnect (transition): {aggregated['total_disconnect_transition']}\n")
        f.write(f"stats rows: {aggregated['total_stats_entries']}\n")
        f.write(f"total send quantity: {aggregated['total_send']}\n")
        f.write(f"error lines captured: {aggregated['errors_total']}\n")
        f.write(f"warning lines captured: {aggregated['warnings_total']}\n")
        f.write(f"debug lines captured: {aggregated['debug_total']}\n\n")
        f.write("Top packets globally:\n")
        for pid, cnt in aggregated["packets_global"].items():
            f.write(f"  0x{pid}: {cnt}\n")

        f.write("Top SEND packet quantities:\n")
        for pid, cnt in aggregated["top_send"].items():
            f.write(f"  0x{pid}: {cnt}\n")

        f.write("Top RECEIVE packet quantities (from STATS):\n")
        for pid, cnt in aggregated["top_receive"].items():
            f.write(f"  0x{pid}: {cnt}\n")

        f.write("\nPeak event windows:\n")
        for w in ("peak_10s", "peak_30s", "peak_120s"):
            peak = aggregated.get(w, {})
            if peak and peak.get("peak_slot") is not None:
                f.write(f"  {w}: slot=+{peak['peak_slot']}s total={peak['peak_total']} top={peak['peak_top']}\n")
            else:
                f.write(f"  {w}: no data\n")

        f.write("\nPer-file details:\n")
        for r in results:
            f.write(f"- {r['file']}: lines={r['total_lines']}, duration={r.get('duration_seconds',0)}s ({format_duration(r.get('duration_seconds',0))}), freeze={r['freeze_count']}, critical={r['critical_count']}, disconnect={r['disconnect_count']}, top: ")
            top = r["packet_counts"].most_common(5)
            f.write(", ".join([f"0x{p}:{c}" for p,c in top]))
            f.write("\n")

            f.write("  window сек => top counts (por janela)\n")
            for window_offset, window_count in sorted(r.get("windows", {}).items(), key=lambda x:int(x[0])):
                topacc = Counter(window_count).most_common(8)
                f.write(f"    +{window_offset}s: " + ", ".join([f"{k}:{v}" for k,v in topacc]) + "\n")

            # detalhamento de erro de textura por arquivo (ID exclusivo)
            if r.get("texture_errors"):
                f.write("  texture errors:\n")
                for k,v in sorted(r["texture_errors"].items(), key=lambda x:x[1], reverse=True):
                    f.write(f"    {k}: {v}\n")

    print(f"Summary written to {out_json} and {out_txt}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze ClassicUO logs and create summary")
    parser.add_argument("--dir", "-d", default=".", help="directory with log files")
    parser.add_argument("--json", default="summary.json", help="json output path")
    parser.add_argument("--txt", default="summary.txt", help="text output path")
    args = parser.parse_args()
    summarize(args.dir, args.json, args.txt)