import serial
import serial.tools.list_ports
import time
import re
from datetime import datetime

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def find_modem_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        try:
            with serial.Serial(port.device, 115200, timeout=1) as ser:
                ser.write(b'AT\r')
                time.sleep(0.5)
                response = ser.read(100).decode(errors='ignore')
                if 'OK' in response:
                    return port.device
        except Exception:
            continue
    return None

def send_and_log(ser, cmd, wait=0.5):
    log(f"SEND: {cmd.strip()}")
    ser.write((cmd + '\r').encode())
    time.sleep(wait)
    resp = b''
    while ser.in_waiting:
        resp += ser.read(ser.in_waiting)
        time.sleep(0.1)
    decoded = resp.decode(errors='ignore')
    if decoded.strip():
        log(f"RECV: {decoded.strip()}")
    return decoded

def try_cnmi_modes(ser):
    cnmi_modes = ["2,2,0,0,0", "1,2,0,0,0", "2,1,0,0,0"]
    for mode in cnmi_modes:
        resp = send_and_log(ser, f'AT+CNMI={mode}')
        if 'OK' in resp:
            log(f"CNMI mode {mode} enabled.")
            return True
    log("No CNMI mode succeeded. Will use polling fallback.")
    return False

def parse_and_show_sms(raw):
    # +CMGL: idx,"stat","sender","alpha","date"
    for match in re.finditer(r'\+CMGL: (\d+),"([^"]+)","([^"]*)","([^"]*)","([^"]*)"\r\n([\s\S]*?)(?=\r\n\+CMGL:|\r\nOK)', raw):
        idx, stat, sender, alpha, date, text = match.groups()
        print(f"\n=== New SMS (index {idx}) ===\nStatus: {stat}\nFrom: {sender}\nDate: {date}\nMessage: {text.strip()}\n========================\n")

def parse_and_show_cmgr(raw):
    # +CMGR: "stat","sender","alpha","date"
    m = re.search(r'\+CMGR: "([^"]+)","([^"]*)","([^"]*)","([^"]*)"\r\n([\s\S]*)', raw)
    if m:
        stat, sender, alpha, date, text = m.groups()
        print(f"\n=== New SMS (direct read) ===\nStatus: {stat}\nFrom: {sender}\nDate: {date}\nMessage: {text.strip()}\n========================\n")

def main():
    log('Searching for modem on COM ports...')
    port = find_modem_port()
    if not port:
        log('No modem found on any COM port.')
        return
    log(f'Modem found on {port}. Initializing...')
    with serial.Serial(port, 115200, timeout=1) as ser:
        # Set text mode
        send_and_log(ser, 'AT+CMGF=1')
        # Try to set storage to SIM, fallback to ME
        resp = send_and_log(ser, 'AT+CPMS="SM","SM","SM"')
        if 'ERROR' in resp:
            send_and_log(ser, 'AT+CPMS="ME","ME","ME"')
        # Enable notifications
        push_ok = try_cnmi_modes(ser)
        # Initial scan: record all existing SMS indexes
        send_and_log(ser, 'AT+CMGL="ALL"')
        shown_indexes = set()
        resp = send_and_log(ser, 'AT+CMGL="ALL"', wait=1)
        for match in re.finditer(r'\+CMGL: (\d+),', resp):
            shown_indexes.add(match.group(1))
        log('Ready. Waiting for new SMS...')
        try:
            last_poll = time.time()
            while True:
                # 1. Real-time notification: check for unsolicited data
                if ser.in_waiting:
                    data = ser.read(ser.in_waiting).decode(errors='ignore')
                    log(f"UNSOLICITED: {data.strip()}")
                    # +CMTI: "SM",index
                    m = re.search(r'\+CMTI: "[A-Z]+",(\d+)', data)
                    if m:
                        idx = m.group(1)
                        # Read the new SMS
                        raw = send_and_log(ser, f'AT+CMGR={idx}', wait=1)
                        parse_and_show_cmgr(raw)
                        shown_indexes.add(idx)
                # 2. Always poll every 10s for new SMS
                if time.time() - last_poll > 10:
                    resp = send_and_log(ser, 'AT+CMGL="ALL"', wait=1)
                    for match in re.finditer(r'\+CMGL: (\d+),"([^"]+)","([^"]*)","([^"]*)","([^"]*)"\r\n([\s\S]*?)(?=\r\n\+CMGL:|\r\nOK)', resp):
                        idx, stat, sender, alpha, date, text = match.groups()
                        if idx not in shown_indexes:
                            print(f"\n=== New SMS (index {idx}) ===\nStatus: {stat}\nFrom: {sender}\nDate: {date}\nMessage: {text.strip()}\n========================\n")
                            shown_indexes.add(idx)
                    last_poll = time.time()
                time.sleep(0.2)
        except KeyboardInterrupt:
            log('Stopped.')

if __name__ == '__main__':
    main()
