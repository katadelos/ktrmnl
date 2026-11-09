#!/bin/sh
# Name: ktrmnl2 power test
# Author: ktrmnl2-k2-variant
# Run from Scriptlets after exiting ktrmnl2 and k2. Disconnect USB when started.
# Logs: /mnt/us/ktrmnl2-power-test/<UTC timestamp>/
set -eu
case "${1:-}" in
    --help)
        cat <<'HELP'
Exit ktrmnl2 and k2, launch this scriptlet, then disconnect USB within 3 minutes.
Do not touch the reader during the automatic phases. Each lasts 5 minutes.
Progress: /mnt/us/ktrmnl2-power-test/STATUS.txt
Latest log directory: /mnt/us/ktrmnl2-power-test/LATEST.txt
Four phases take about 25 minutes. The final phase uses stock powerd sleep.
If still asleep after 35 minutes, press Power once to wake it and allow cleanup.
Brightness, Wi-Fi enable state and screensaver policy are restored on exit.
Run again only after STATUS.txt reports COMPLETE or FAILED.
HELP
        exit 0 ;;
    --worker) ;;
    '')
        base=/mnt/us/ktrmnl2-power-test
        mkdir -p "$base"
        run="$base/$(date -u +%Y%m%dT%H%M%SZ)-$$"
        mkdir "$run"
        # The worker keeps the lock; Scriptlets can return to the stock UI.
        nohup /bin/sh /mnt/us/.eink-sdk/control/run /bin/sh "$0" --worker "$run" \
            >"$run/launcher.log" 2>&1 </dev/null &
        exit 0 ;;
    *) echo 'Use --help for instructions.' >&2; exit 2 ;;
esac
exec /var/run/eink-sdk/usr/bin/python3 - "$2" <<'PYTHON'
import csv
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import traceback

RUN = Path(sys.argv[1])
SECONDS = 300
POWERD = "com.lab126.powerd"
WIFID = "com.lab126.wifid"
CMD = "com.lab126.cmd"
STOCK_ENV = {k: v for k, v in os.environ.items()
             if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH")}
STOCK_ENV["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
events = (RUN / "events.jsonl").open("a", buffering=1)
lock = (RUN.parent / "lock").open("w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Another power test is running; see ktrmnl2-power-test/STATUS.txt.")
# Kindle user storage is FAT: use ordinary files, not symlinks.
(RUN.parent / "LATEST.txt").write_text(str(RUN) + "\n")


def clocks():
    return {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "epoch": time.time(), "monotonic": time.monotonic(),
            "boottime": time.clock_gettime(time.CLOCK_BOOTTIME)}


def log(kind, **data):
    events.write(json.dumps({**clocks(), "event": kind, **data}) + "\n")
    events.flush()
    os.fsync(events.fileno())


def status(message):
    (RUN / "STATUS.txt").write_text(message + "\n")
    (RUN.parent / "STATUS.txt").write_text(message + "\nLog directory: " + str(RUN) + "\n")
    log("status", message=message)


def command(*args, required=True):
    p = subprocess.run(args, env=STOCK_ENV, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=15)
    if p.returncode and required:
        raise RuntimeError(f"{args[0]} {args[1:]}: {p.stderr.strip()}")
    return p.stdout.strip()


def get(service, name):
    return command("lipc-get-prop", service, name)


def put(service, name, value):
    command("lipc-set-prop", service, name, str(value))
    log("property_set", service=service, property=name, value=value)


def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError) as exc:
        return f"unavailable: {exc}"


def light_state():
    return {str(p): {n: read(p / n) for n in
                    ("brightness", "actual_brightness", "bl_power", "max_brightness")}
            for p in Path("/sys/class/backlight").glob("*")}


def supplies():
    # Do not copy device serial numbers or application credentials.
    fields = ("type", "online", "status", "capacity", "voltage_now", "current_now",
              "current_avg", "charge_now", "charge_counter", "charge_full", "temp")
    return {str(p): {n: read(p / n) for n in fields if (p / n).exists()}
            for p in Path("/sys/class/power_supply").glob("*")}


def connected_power():
    external = [v for v in supplies().values() if v.get("type") in
                ("Mains", "USB", "USB_DCP", "USB_CDP", "USB_ACA", "USB_C", "USB_PD")]
    if not external:
        raise RuntimeError("Cannot identify external power; refusing a charging measurement.")
    if any(v.get("online") not in ("0", "1") for v in external):
        raise RuntimeError("External-power readback is unavailable; measurement refused.")
    return any(v.get("online") == "1" for v in external)


def snapshot(label):
    kernel = command("dmesg", required=False)
    (RUN / f"{label}.dmesg.txt").write_text(kernel + "\n")
    try:
        with open("/var/log/messages", "rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 262144))
            lines = stream.read().decode(errors="replace").splitlines()
        selected = [line for line in lines if "powerd[" in line or
                    ("wifid[" in line and "spectator:" in line) or
                    ("cmd[" in line and "statechange:" in line)]
        (RUN / f"{label}.stock-log.txt").write_text("\n".join(selected) + "\n")
    except OSError as exc:
        log("stock_log_unavailable", error=str(exc))
    state = {**clocks(), "label": label, "supplies": supplies(),
             "light": light_state(), "powerd_state": get(POWERD, "state"),
             "wifi_enabled": get(WIFID, "enable"),
             "wireless_enabled": get(CMD, "wirelessEnable"),
             "wifi_state": command("lipc-get-prop", WIFID, "cmState", required=False),
             "net_interfaces": {str(p): {n: read(p / n) for n in
                                         ("operstate", "flags", "carrier")}
                                for p in Path("/sys/class/net").glob("*")},
             "modules": read("/proc/modules"),
             "gauge_lines": [l for l in kernel.splitlines() if "clamp_soc:" in l][-5:],
             "kernel": {p: read(p) for p in (
                 "/proc/uptime", "/sys/power/state", "/sys/power/wake_lock",
                 "/sys/kernel/debug/suspend_stats", "/sys/kernel/debug/wakeup_sources",
                 "/sys/class/rtc/rtc0/wakealarm")}}
    (RUN / f"{label}.json").write_text(json.dumps(state, indent=2) + "\n")
    log("snapshot", label=label)
    return state


def verify_light_off():
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = light_state()
        # actual_brightness is the available physical readback; a LIPC value
        # alone is not sufficient. Require zero continuously across a settle.
        if state and all(v["actual_brightness"] == v["brightness"] == "0"
                         for v in state.values()):
            time.sleep(2)
            settled = light_state()
            if settled.keys() == state.keys() and all(
                    v["actual_brightness"] == v["brightness"] == "0"
                    for v in settled.values()):
                log("light_off_verified", light=settled)
                return
        time.sleep(.25)
    raise RuntimeError("Frontlight did not report physical zero; see logged readback.")


def check_unplugged():
    if connected_power():
        raise RuntimeError("USB/external power detected; measurement aborted.")


def active_sdk_apps():
    found = []
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            argv = (proc / "cmdline").read_bytes().split(b"\0")
            if any(a in (b"ktrmnl2.device", b"k2.adapters.session", b"k2.app") for a in argv):
                found.append(int(proc.name))
        except OSError:
            pass
    return found


def interrupted(signum, frame):
    raise RuntimeError(f"Interrupted by signal {signum}")


for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, interrupted)

original = None
device = None
retained = False
rows = []
failure = None
try:
    from ereader_hal import Device

    apps = active_sdk_apps()
    if apps:
        raise RuntimeError(f"Exit ktrmnl2 and k2 first (running PIDs: {apps}).")
    if get(POWERD, "state") != "active" or int(get(POWERD, "preventScreenSaver")):
        raise RuntimeError("Start from the active stock UI with no screensaver inhibitor.")
    device = Device()
    if device.get_battery().percent < 20:
        raise RuntimeError("Charge above 20% before testing.")
    original = {"light": int(get(POWERD, "flIntensity")),
                "wifi": int(get(WIFID, "enable")),
                "wireless": int(get(CMD, "wirelessEnable")),
                "prevent": int(get(POWERD, "preventScreenSaver"))}
    (RUN / "original-state.json").write_text(json.dumps(original, indent=2) + "\n")
    snapshot("initial")
    status("WAITING: disconnect USB within 3 minutes. Leave the reader untouched.")
    deadline = time.monotonic() + 180
    while connected_power():
        if time.monotonic() >= deadline:
            raise RuntimeError("USB remained connected; no tests performed.")
        time.sleep(2)
    time.sleep(10)
    device.retain_display()
    retained = True

    for name, verify, radio_off in (
        ("hal_app_sequence", False, False),
        ("hal_verified_light_off", True, False),
        ("hal_verified_light_wifi_disabled", True, True),
    ):
        status(f"RUNNING: {name}; {SECONDS}s requested sleep. Do not touch the reader.")
        if radio_off:
            device.set_wifi(False)
        else:
            put(CMD, "wirelessEnable", original["wireless"])
            put(WIFID, "enable", original["wifi"])
        put(POWERD, "flIntensity", original["light"])
        time.sleep(35)  # Let the gauge and restored hardware settle while awake.
        check_unplugged()
        before = snapshot(name + "-before")
        start = clocks()
        result = {}
        try:
            log("suspend_call", phase=name, light_before=light_state(), seconds=SECONDS)
            device.set_frontlight(False)
            if verify:
                verify_light_off()
            if radio_off and (int(get(WIFID, "enable")) != 0 or
                              int(get(CMD, "wirelessEnable")) != 0):
                raise RuntimeError("Wi-Fi disable request was not applied.")
            # No retry here: EBUSY and an early wake are diagnostic results.
            device.suspend_for(SECONDS)
            result = {"hal_slept_ms": device.get_last_sleep_ms(),
                      "hal_sleep_gap_ms": device.get_last_sleep_gap_ms(),
                      "wake_reason": device.get_last_wake().reason.name}
        except OSError as exc:
            result = {"error": str(exc), "errno": exc.errno}
        finally:
            end = clocks()
            log("suspend_return", phase=name, result=result, start=start, end=end)
            snapshot(name + "-wake")
            put(POWERD, "flIntensity", original["light"])
        check_unplugged()
        time.sleep(35)  # Capture a fresh post-wake fuel-gauge kernel sample.
        after = snapshot(name + "-after")
        elapsed = end["boottime"] - start["boottime"]
        asleep = max(0, elapsed - (end["monotonic"] - start["monotonic"]))
        rows.append({"phase": name, "requested_s": SECONDS,
                     "elapsed_s": round(elapsed, 3), "sleep_gap_s": round(asleep, 3),
                     "valid": "error" not in result and asleep >= SECONDS * .8,
                     "result": json.dumps(result)})
        log("phase_complete", **rows[-1])
        if "error" in result or asleep < SECONDS * .8:
            log("invalid_comparison", phase=name,
                reason="Suspend refused or woke early; do not compare this as a full sleep.")

    name = "stock_powerd"
    status("RUNNING: stock_powerd; expected automatic wake after 5 minutes asleep. "
           "If this phase has not returned after 8 minutes, press Power once.")
    put(CMD, "wirelessEnable", original["wireless"])
    put(WIFID, "enable", original["wifi"])
    time.sleep(35)
    check_unplugged()
    snapshot(name + "-before")
    # powerd accepts rtcWakeup during readyToSuspend, not while active.
    # Subscribe before requesting the screensaver; let powerd own its RTC.
    listener = subprocess.Popen(
        ["lipc-wait-event", "-m", POWERD, "readyToSuspend,wakeupFromSuspend"],
        env=STOCK_ENV, stdout=subprocess.PIPE, stderr=(RUN / "stock-events.stderr").open("w"))
    os.set_blocking(listener.stdout.fileno(), False)
    stock_start = clocks()
    armed = False
    try:
        time.sleep(1)
        if listener.poll() is not None:
            raise RuntimeError("Stock event subscription failed.")
        put(POWERD, "touchScreenSaverTimeout", 1)
        device.release_display()
        retained = False
        put(POWERD, "powerButton", 1)
        pending = b""
        while True:
            now = clocks()
            elapsed = now["boottime"] - stock_start["boottime"]
            asleep = max(0, elapsed - (now["monotonic"] - stock_start["monotonic"]))
            if asleep > 2:
                break
            check_unplugged()
            # This bounds awake observation only; Python cannot enforce a
            # deadline while suspended if the stock wake alarm was not armed.
            if elapsed > SECONDS + 180 or (not armed and elapsed > 120):
                raise RuntimeError("Stock sleep did not occur within its observation window.")
            if listener.poll() is not None:
                raise RuntimeError("Stock event listener exited before sleep.")
            readable, _, _ = select.select([listener.stdout], [], [], 1)
            if readable:
                pending += os.read(listener.stdout.fileno(), 8192)
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    event = line.decode(errors="replace")
                    log("powerd_event", value=event)
                    if "readyToSuspend" in event and not armed:
                        put(POWERD, "rtcWakeup", SECONDS)
                        armed = True
                        log("stock_alarm_requested", seconds=SECONDS)
        log("stock_return", elapsed_s=elapsed, sleep_gap_s=asleep, alarm_requested=armed)
        snapshot(name + "-wake")
        rows.append({"phase": name, "requested_s": SECONDS,
                     "elapsed_s": round(elapsed, 3), "sleep_gap_s": round(asleep, 3),
                     "valid": armed and asleep >= SECONDS * .8,
                     "result": json.dumps({"stock_alarm_requested": armed,
                                           "full_interval": asleep >= SECONDS * .8})})
        log("phase_complete", **rows[-1])
    finally:
        listener.terminate()
        try:
            listener.wait(timeout=5)
        except subprocess.TimeoutExpired:
            listener.kill()
            listener.wait()
        # Never clear sysfs RTC here: powerd may have alarms from other clients.
        # An interrupted stock phase can leave its one-shot wake pending.
        put(POWERD, "wakeUp", 1)
    device.retain_display()
    retained = True
    check_unplugged()
    time.sleep(35)
    snapshot(name + "-after")
except BaseException as exc:
    failure = str(exc)
    log("failure", error=failure, traceback=traceback.format_exc())
finally:
    # Restore each setting independently, even if another restoration fails.
    restore_errors = []
    if device is not None:
        for action in ([device.release_display] if retained else []) + [device.close]:
            try:
                action()
            except Exception as exc:
                restore_errors.append(str(exc))
    if original is not None:
        for service, prop, value in ((CMD, "wirelessEnable", original["wireless"]),
                                     (WIFID, "enable", original["wifi"]),
                                     (POWERD, "flIntensity", original["light"]),
                                     (POWERD, "preventScreenSaver", original["prevent"])):
            try:
                put(service, prop, value)
                if int(get(service, prop)) != value:
                    raise RuntimeError("Readback does not match saved value")
            except Exception as exc:
                restore_errors.append(f"{service}.{prop}: {exc}")
        try:
            snapshot("restored")
        except Exception as exc:
            restore_errors.append(f"Final snapshot: {exc}")
    with (RUN / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("phase", "requested_s", "elapsed_s",
                                                   "sleep_gap_s", "valid", "result"))
        writer.writeheader()
        writer.writerows(rows)
    log("restoration", errors=restore_errors)
    if restore_errors:
        failure = (failure or "Restoration incomplete") + "; " + "; ".join(restore_errors)
    status(("FAILED: " + failure) if failure else
           "COMPLETE: settings restored. See summary.csv and events.jsonl. "
           "Early wakes/failed phases are not valid full-interval comparisons.")
    events.close()
sys.exit(1 if failure else 0)
PYTHON
